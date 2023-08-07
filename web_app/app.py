try:
  import unzip_requirements
except ImportError:
  pass

import warnings
warnings.filterwarnings('ignore')

import os
import json
import yaml
import codecs
from datetime import datetime

import pytz
from io import BytesIO
from dotenv import load_dotenv

import numpy as np
import pandas as pd

from scipy.spatial import distance
from sklearn.metrics.pairwise import cosine_similarity

import sqlalchemy
import snowflake

import urllib

from flask import Flask, render_template, request, redirect, jsonify, Response


# Class for skills matching scoring
class SkillsMatcher:
    def __init__(self,
                 skills_input, #Input from the form (skills' names, levels and weights)
                 default_cols, # Default columns in the output table
                 output_cols, # Additional output columns (for volunteers / mentors)
                 X_const, # Constant variable for penalizing missing skills
                 skill_y_lvl_n_name, # Indicator for non-missing skill with missing level
                 skill_n_lvl_n_name # Indicator for missing skill and missing level
                 ):

        # List of skills names'
        self.input_skills = list(skills_input.keys())
        # Dictionary of skills names, levels and weights
        self.input_skills_levels = skills_input
        # Output columns in the result table
        self.display_columns = default_cols + [f'{i}_level' for i in self.input_skills_levels.keys()] + output_cols
        # Scoring column name (Assuming its in the last position of the list)
        self.scoring_name = default_cols[-1]
         # Indicator for non-missing skill with missing level
        self.skill_y_lvl_n_name = skill_y_lvl_n_name
        # Indicator for missing skill and missing level
        self.skill_n_lvl_n_name = skill_n_lvl_n_name
        # Constant variable for penalizing missing skills
        self.X_const = X_const
        
        # 0-1 matrix of baseline and the volunteers/mentors (w.r.t. skills' occurrences)
        self.indicator_skills_matrix = None
        # Matrix of baseline and the volunteers/mentors (w.r.t. skills' levels and weights)
        self.lvl_skills_matrix = None
        # Matrix of inverses of distances of baseline and the volunteers/mentors
        self.inv_dist_matrix = None
        


    # Data Preparation for scoring
    def preprocess_data(self, preprocessed_df):

        self.preprocessed_df = preprocessed_df.copy()
       
        # Baseline vector for cosine similarity (based on the input skills)
        baseline = pd.DataFrame({k: 1 for k in self.input_skills}, index = [0])

        # Volunteers'/Mentors' skills
        df_skills = self.preprocessed_df[self.input_skills].copy()

        # Joining the baseline and the skills matrix of volunteers/mentors
        df_skills = pd.concat((baseline, df_skills)).reset_index(drop = True)

        # 0-1 matrix of baseline and the volunteers/mentors (w.r.t. skills' occurrences)
        self.indicator_skills_matrix = df_skills.values

        return self.indicator_skills_matrix


    # Scoring of the skills' occurrences - cosine similarity
    def skills_indicator(self, preprocessed_df):

        preprocessed_df = preprocessed_df.copy()

        # Similarity based on cosine similarity
        similarity_matrix = cosine_similarity(self.indicator_skills_matrix)

        # 1st row indicates the cosine scores for the baseline vector with others starting from 2nd position
            # i.e., excluding the score of the baseline with itself
        self.preprocessed_df['cosine_score'] = similarity_matrix[0, 1:]

        return self.preprocessed_df



    def similarity_matching(self, preprocessed_df):

        # Data preparation
        preprocessed_df = self.preprocess_data(preprocessed_df)

        # Cosine scoring
        cosine_scoring_df = self.skills_indicator(preprocessed_df)

        # Filtering non-zero cosine scores
            # i.e., excluding the users with no matches
        output_df = cosine_scoring_df.query('cosine_score > 0').reset_index(drop = True).copy()

        # Baseline vector of skills' levels
        baseline = pd.DataFrame({f'{k}_level': v['level'] for k, v in self.input_skills_levels.items()},
                                index=['baseline']).rename_axis('id')
        # Volunteers'/Mentors' skills' levels
        df_skills = output_df[[f'{i}_level' for i in self.input_skills_levels.keys()]]

        # Joining the baseline and the skills' levels matrix of volunteers/mentors
        df_skills = pd.concat((baseline, df_skills))

        # Encoding the string skills' levels into numeric levels
        for col, level_weight in zip([f'{i}_level' for i in self.input_skills_levels.keys()], self.input_skills_levels.values()):
            
            # Optional weigthing for penalizing the dissimilarity of the skills' levels w.r.t. baseline
            try:
                level = level_weight['level']
                weight = level_weight['weight']
            except:
                level = level_weight['level']
                weight = 1

            ## The volunteers/mentors who have the same skill level for given skill as the baseline has numeric value:
                # These volunteers/mentors will then have 0 distance -> perfect similarity score for given skill
            ## The volunteers/mentors with the nearest higher level will have lower non-value than the volunteers/mentors with the nearest lower level, w.r.t. baseline:
                # e.g., if we look for Python mediors, hence Python seniors will have higher scores than Python juniors (we prefer higher level over lower level)
            ## If the skill level is missing, but the volunteer/mentor has given skill, then it will have the the highest value (higher distance) than the other skill values (junior, medior, senior, mentor)
            ## If the skill level missing and the volunteer/mentor does not have given skill, then it will have the highest possible value given by the X_const (i.e., the highest distance) (the least preferred option)
                # This is applicable when we required more than one skill, hence through the cosine filtering will pass any volunteers/mentors having at least one skill in common w.r.t. baseline.
            ## Special case is if the baseline's skill level is empty, i.e., we do not prefer any skill level, just the skill itself.
                # Hence all the volunteers/mmentors who have non-empty skill level for given skill (junior/medior/senior/mentor) or have given skill but missing skill level, will have value 0 -> zero distance -> higher score
                # All the others will have non-zero value given by X_const.

            if level == 'junior':
                df_skills[col] = weight * df_skills[col].replace({'junior': 0, 'medior': 0.25,'senior': 0.5, 'mentor': 0.75,
                                                                  self.skill_y_lvl_n_name: 1, self.skill_n_lvl_n_name: self.X_const})
            elif level == 'medior':
                df_skills[col] = weight * df_skills[col].replace({'junior': 0.5, 'medior': 0, 'senior': 0.25, 'mentor': 0.75,
                                                                  self.skill_y_lvl_n_name: 1, self.skill_n_lvl_n_name: self.X_const})
            elif level == 'senior':
                df_skills[col] = weight * df_skills[col].replace({'junior': 0.75, 'medior': 0.5, 'senior': 0, 'mentor': 0.25,
                                                                  self.skill_y_lvl_n_name: 1, self.skill_n_lvl_n_name: self.X_const})
            elif level == 'mentor':
                df_skills[col] = weight * df_skills[col].replace({'junior': 0.75, 'medior': 0.5, 'senior': 0.25, 'mentor': 0,
                                                                  self.skill_y_lvl_n_name: 1, self.skill_n_lvl_n_name: self.X_const})
            else:
                df_skills[col] = [weight * self.X_const if i == self.skill_n_lvl_n_name else 0 for i in df_skills[col]]

        # Matrix of baseline and the volunteers/mentors (w.r.t. skills' levels and weights)
        self.lvl_skills_matrix = df_skills.values

        # Calcuation of inverse of the distance metrics:
            # Euclidean, Manhattan and Mahalanobis
            # Absolute (cumulative) distances normed by the number of skills -> average distances
            # Inverse distance -> similarity score: 1 / (avg_dist + 1) --> zero distance --> 100% score

        euclidean_dist = distance.squareform(distance.pdist(self.lvl_skills_matrix, metric = 'euclidean'))
        euclidean_similarity_matrix = 1 / (euclidean_dist / len(self.input_skills)  + 1)
        output_df['euclidean_score'] = euclidean_similarity_matrix[0, 1:]

        manhattan_dist = distance.squareform(distance.pdist(self.lvl_skills_matrix, metric = 'cityblock'))
        manhattan_similarity_matrix = 1 / (manhattan_dist / len(self.input_skills) + 1)
        output_df['manhattan_score'] = manhattan_similarity_matrix[0, 1:]

        # Final inverses' average distances' matrix as an average of of inverses' average distances
        try:
            mahalanobis_dist = distance.squareform(distance.pdist(self.lvl_skills_matrix, metric='mahalanobis'))
            mahalanobis_similarity_matrix = 1 / (mahalanobis_dist / len(self.input_skills) + 1)
            output_df['mahalanobis_score'] = mahalanobis_similarity_matrix[0, 1:]
            
            # Average of all the three inverses' average distances
            self.inv_dist_matrix = np.mean([euclidean_similarity_matrix, manhattan_similarity_matrix, mahalanobis_similarity_matrix], axis = 0)
        except:
            # Average of all inverses' average Euclidean and Manhattan distances only, without Mahalanobis distance
                # Due to the singularity matrix for inverse - this happens when the baseline has only one skill without required level.
                    # Hence after cosine scoring, it will keep all the users having given skill.
                    # Since there are not users without given skill, all users will have zero numeric value
                    # Hence, the variance will be zero which is reflected in covariance matrix
                    # Hence it does not have inverse since is has zero determinant.

            self.inv_dist_matrix = np.mean([euclidean_similarity_matrix, manhattan_similarity_matrix], axis = 0)

        # Assigning the final score to the result table
        output_df[self.scoring_name] = np.round(self.inv_dist_matrix[0, 1:], 2)

        # Final result table, including the respective output columns and sorted respectively by score.
        output_df = output_df[self.display_columns].sort_values(by = self.scoring_name, ascending = False).copy()

        return output_df


## Function for checking the login credentials
def check_authentication(username, password, cred_username, cred_password):

    if (cred_username == username) and (cred_password == password):
        return True

    else:
        return False



## Function for preparning email template based on the default template
 # it will insert the respective fields for position name, link and description
def prep_email_template(positions, email_template, config):

    with codecs.open(email_template, 'r', encoding = 'utf-8') as file:
        body_email = file.read()

    body_email = (body_email
                      .replace(config['email_inputs']['name'], positions['name'])
                      .replace(config['email_inputs']['desc'], positions['desc'])
                      .replace(config['email_inputs']['link'], positions['link'])
                      )

    return body_email


## Function for opening a new gmail message template with inserted subject, body text and Bcc.
def open_gmail_new_message(bcc, subject, body):

    url = f"https://mail.google.com/mail/?view=cm&fs=1&tf=1&bcc={bcc}&su={subject}&body={body}"
    
    return url




# Loading the environmen tvariables (such as credentials)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inputs', '.env'))

# Lpading configuration file for data frame operations
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                        'inputs', 'config.yaml'),
                        'r',  encoding='utf-8') as f:
    
    config = yaml.safe_load(f)




# Flask app initialization
app = Flask(__name__)


# Global variables which will be assigned in the app later
position_info = None
body_email = None
skills_output_excel = None


# Login page
@app.route('/')
def login():

    # Render the login page
    return render_template('login.html')



# Login form
@app.route('/login', methods=['POST'])
def get_login():

    # Retrieved login credentials from the login form
    username = request.form.get('username')
    password = request.form.get('password')

    # Correct login credentials
    app_username = os.getenv('app_username')
    app_password = os.getenv('app_password')

    # Check the login credentials
    authenticated = check_authentication(username, password, app_username, app_password)

    if authenticated:
        # Redirect to the skill form page
        return redirect('/form')
    
    else:
        error = "Invalid username or password"
        # Render the login page again with the error message
        return render_template('login.html', error = error)




# Input skills form page
@app.route('/form')
def skills():

    # Render the skill form page
    return render_template('form.html')




# Result page with an output table
@app.route('/result', methods=['POST'])
def result():
    
    # Read JSON file for mapping skills' names (columns' names -> names with diacritics)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           config['input_dir'],
                           config['skills_map']), 'r') as f:
        
        skills_map = json.load(f)


    ## Accessing email template path
    email_template = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    config['input_dir'],
                                    config['email_template'])
    
    # Dictionary for storing the skills and their respective levels from the form
    skills_flask_input = {}

    # Mentor / Volunteer (retrieved from the form)
    looking_for = request.form.get('looking-for')

    # Accessing filled position' name, link and description
    position_name = request.form.get('position_name0')
    position_link = request.form.get('position_link0')
    position_description = request.form.get('position_description0')

    # Storing position information dictiionary with the inputs from the form
    global position_info 
    position_info = {'name': position_name, 'link': position_link, 'desc': position_description}

    # Preparing and storing new email template with the position's information
    global body_email
    body_email = prep_email_template(position_info, email_template, config)


    # Reading input skills properties (name / level / weight) from the form
    for key, value in request.form.items():

        # Obtain skills properties' inputs
        if key.startswith('option_skill'):

            skill_name = skills_map[value]
            level = request.form.get(f'level_skill{key.split("option_skill")[1]}').lower()
            weight = request.form.get(f'skill_weight{key.split("option_skill")[1]}')

            # Accessing weights - if not filled, default weight is 1
            if weight:
                weight = float(weight)
            else:
                weight = 1.0

            # Storing the baseline input skills properties into a dictionary
            skills_flask_input[skill_name] = {'level': level, 'weight': float(weight)}

    # Snowflake credentials
    snowflake_account = os.getenv('snowflake_account')
    snowflake_user = os.getenv('snowflake_user')
    snowflake_password = os.getenv('snowflake_password')
    snowflake_warehouse = os.getenv('snowflake_warehouse')
    snowflake_database = os.getenv('snowflake_database')
    snowflake_schema = '"{}"'.format(os.getenv('snowflake_schema'))

    # Snowflake connection to the volunteers' / mentors' table
    table_name = os.getenv(f'snowflake_{looking_for.lower()}')
    sql_query = f'select * from "{table_name}"'

    try:
        conn = (
                f"snowflake://{snowflake_user}:{snowflake_password}"
                f"@{snowflake_account}/"
                f"?warehouse={snowflake_warehouse}"
                f"&database={snowflake_database}"
                f"&schema={snowflake_schema}"
            )
        
        engine = sqlalchemy.create_engine(conn)
        processed_df = pd.read_sql_query(sql_query, engine)

    except:
        conn = snowflake.connector.connect(
                                            account = snowflake_schema,
                                            user = snowflake_user,
                                            password = snowflake_password,
                                            warehouse = snowflake_warehouse,
                                            database = snowflake_database,
                                            schema = snowflake_schema
                                        )

        processed_df = pd.read_sql_query(sql_query, conn)


    # Keboola bug - it somehow adds an extra underscore to several columns names and remove diacritics
    for col in processed_df.columns:
        if '____level' in col:
            processed_df = processed_df.rename(columns={col: col.replace('____level', '_level')})
        elif '__level' in col:
            processed_df = processed_df.rename(columns={col: col.replace('__level', '_level')})


    # Excluding Internal Team users, i.e., the employees of Cesko.Digital
    try:
        processed_df = processed_df[processed_df[config['drop_rows']['col']] != config['drop_rows']['val']]
    except:
        pass
    
    # Reset the row indices
    processed_df = processed_df.reset_index(drop = True)


    # Creating column listing all other skills for each volunteer / mentor
    skills_set = set(skills_map.values())

    # If the skill is missing in given table, add the skill column with 0's (indicating non-occurrence of given skill)
    # And/or if the skill level column is missing in given table,
        # add the skill level column with empty strings (indicating missing level for given given skill)
    # These steps are required for scoring/distance calculations

    for skill in skills_set:
        if skill not in processed_df.columns:
            processed_df[skill] = 0
        if f'{skill}_level' not in processed_df.columns:
            processed_df[f'{skill}_level'] = ''

    # List of other skills for each volunteer/mentor
    processed_df[config['other_skills']] = (processed_df[skills_set]
                                   .apply(lambda row: [
                                            # Get mapped skills' names based columns' nnames
                                            {v: k for k, v in skills_map.items()}.get(val) 
                                                    # Access only skills which given user has
                                                    for val in row[row.isin(['1', 1])].index 
                                                        # Remove actual required skills and keep only the other skills
                                                        if val not in skills_flask_input.keys() and val in skills_set 
                                                    ],
                                            axis = 1
                                        )
                                    )
    
    # Adding skill levels information to the other skills
    processed_df[config['other_skills']] = (processed_df
                                   .apply(lambda row:
                                        # Join the skills strings with the levels into one string
                                        ' / '.join([f'{skill} ({row[skills_map[skill]+"_level"].capitalize()})'
                                            # Put the skill level into parentheses
                                            # If skill level is empty, keep only the skill names w/o skill level
                                            if len(row[skills_map[skill] + "_level"].capitalize()) > 0 else skill
                                                for skill in row['OtherSkills']]), axis = 1)
                                   )
    for col in skills_set:
        # Keboola / Snowflake stores the skill indicators (0/1) as strings -> we conver them into numerics
        processed_df[col] = processed_df[col].astype('float')

        # Remapping None skill levels based on whether the skill is available
            # If the skill is not missing, but the level is missing -> 'N/A level'
            # If both the skill and level are missing -> 'X'

        processed_df[f'{col}_level'] = [
                                            config['mapping_lvl_nan']['skill_y_lvl_n']
                                                if lvl == '' and ind == 1
                                            else config['mapping_lvl_nan']['skill_n_lvl_n']
                                                if lvl == '' and ind == 0
                                            else lvl
                                            for ind, lvl in zip(processed_df[col],
                                                                processed_df[f'{col}_level'])
                                            ] 
    
    # Scoring the skills using the SkillsMatcher based on:
        # Skill inputs from the form as a baseline
        # Default output columns, i.e., name, ID, email
        # variable output columns, depending on the volunteer / mentor selection
        # Constant value for penalizing missing skills
        # Indicator for non-missing skill with missing level
        # Indicator for missing skill and missing level
    
    # Output columns in the result table
    default_out_cols = config['out_cols']['default']
    opt_output_cols = config['out_cols'][looking_for.lower()]

    # Skill Matching Scoring object initialization
    skills_level_matcher = SkillsMatcher(skills_flask_input, # Skills iinput from the form - baseline
                                         default_out_cols, # Default output columns
                                         opt_output_cols, # Variable output columns
                                         config['X_const'], # Constant variable for penalizing missing skills
                                         config['mapping_lvl_nan']['skill_y_lvl_n'], # Indicator for non-missing skill with missing level
                                         config['mapping_lvl_nan']['skill_n_lvl_n'] # Indicator for missing skill and missing level
                                         )
    
    # Scoring - result table
    skills_output = skills_level_matcher.similarity_matching(processed_df)


    # Renaming the skill names in the result table (with diacritics)
    skills_output = skills_output.rename(columns = {f'{v}_level': k for k, v in skills_map.items() if f'{v}_level' in skills_output.columns})

    
    # Capitalizing the skill levels
    skills_map_reversed = {v:k for k, v in skills_map.items()}

    for skill_col in skills_flask_input.keys():
        skills_output[skills_map_reversed[skill_col]] = (
                                                        skills_output[skills_map_reversed[skill_col]]
                                                         .replace(config['lvl_map'])
                                                         )



    # Converting floats as string into integers in the oouput columns (if possible)
        # They contain empty strings instead N/A, thus we need to replace them first
        # Since the string values have decimals, we then convert them into floats (cannot be converted directly into integers
        # Then finally we convert floats into integers
        for col in opt_output_cols:
            try:
                skills_output[col] = skills_output[col].replace({'': np.nan}).astype('float').astype('Int64')
            except:
                continue
           
    # Converting date columns from YYYY-MM-DD to DD.MM.YYYY if possible:
    try:
        skills_output[config['last_email_sent']] = (
                                                    pd.to_datetime(skills_output[config['last_email_sent']])
                                                    .dt.strftime('%d.%m.%Y')
                                                    .fillna('')
                                                    )
    except:
        pass

    # Renaming the ouput columns from English to Czech
    skills_output = skills_output.rename(columns = config['translate']['default'] | config['translate'][looking_for.lower()])

    # Obtaining the date of the last update in the SnowFlake databases
    last_updated = datetime.strptime(str(processed_df[config['timestamp']].iloc[0]), '%Y-%m-%d %H:%M:%S').strftime('%d. %m. %Y')

    # Sorting the result table by score and additionaly by other columns (such as days since registered)
    skills_output = skills_output.sort_values(by = config['sort'][looking_for.lower()]['cols'],
                                              ascending = config['sort'][looking_for.lower()]['ascending']).reset_index(drop = True)    
    
    # Renaming the project indicator column's values from English to Czech
    skills_output[config['on_project_now']['col']] = (
                                                      skills_output[config['on_project_now']['col']]
                                                      .replace(config['on_project_now']['val'])
                                                      )
    
    # Replace N/A with 0 for the number of past projects in Cesko.Digitall
    skills_output[config['project_count']] = skills_output[config['project_count']].fillna(0)

    # Storing the result table as a variable for Excel output
    global skills_output_excel
    skills_output_excel = skills_output.copy()

    # Insert a column with checkboxes for sending emails into HTML template
    checkbox_html = '<input type="checkbox" name="checkbox{{ loop.index0 }}" class="email-checkbox">'
    skills_output.insert(0, config['send_email'], checkbox_html)
    
    # If the table contains column with URL links, add HTML codes for hyperlinks
    try:
        skills_output[config['profile']] = skills_output[config['profile']].apply(lambda x: f'<a href="{x}" target="_blank">{x}</a>') 
    except:
        pass

    # Redirect to the result table page with the result table and the last update date
    return render_template('result.html',
                           table = skills_output.to_html(index = False, escape = False),
                           last_updated = last_updated)




# Open new tab with the list of all available skills
@app.route('/skills')
def new_page():
    return render_template('skills.html')




# Download output table as Excel file
@app.route('/download')
def download():

    # Object for in-memory streaming of binary I/O operations
    output = BytesIO()

    # Writing the result table into the stream
    with pd.ExcelWriter(output, engine = 'xlsxwriter') as writer:
        skills_output_excel.to_excel(writer, sheet_name = 'SkillsMatching', index = False)
    
    # Resetting the stream position
    output.seek(0)
    
    # Current datetime inserted into Excel file name
    current_datime = datetime.now(pytz.timezone('Europe/Prague')).strftime("%Y-%m-%d_%Hh%Mm")

    response = Response(
        output,
        # Media application type with binary data in Excel -> allows the web broswer to handle the result table
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        # HTTP header for local download and save the result table
        headers= {"Content-disposition": f"attachment; filename = SkillsMatching_{current_datime}.xlsx"}
    )

    return response




# Send email to selected volunteers / mentors
@app.route('/prep_email', methods=['POST'])
def email():

    # Retrieving the selected volunteers / mentors from the HTML page
    selected_users = pd.DataFrame(request.get_json())

    # Email's features
    bcc = ','.join(selected_users[config['email']].tolist())
    subject = urllib.parse.quote(f'Česko.Digital: {position_info["name"]}')
    body = urllib.parse.quote(body_email.replace('\n', ''))

    # Opening a new email message in Gmail with the email's features
    url = open_gmail_new_message(bcc, subject, body)


    # Redirect to the Gmail URL template
    return jsonify({"url": url})




# Running the web app
if __name__ == '__main__':
    app.run(debug = True, host = '0.0.0.0')