$(document).ready(function(){
    var counter = 1;
    
    function enableAutocomplete(input) {
        $(input).autocomplete({
            source: availableOptions,
            appendTo: 'body'
        });
    }

    enableAutocomplete('input[name="option_skill0"]');

    $("#add-more").click(function(e){
        e.preventDefault();
        var newInputRow = $(`<div class="input-row" id="row${counter}">
            <div class="form-group">
                <label for="option_skill${counter}">Skill Name</label>
                <input type="text" id="option_skill${counter}" name="option_skill${counter}" placeholder="Type skill ..." class="form-control" required>
                <span class="error-message"></span>
            </div>
            <div class="form-group">
                <label for="level_skill${counter}">Skill Level (Optinal)</label>
                <select id="level_skill${counter}" name="level_skill${counter}" class="form-control">
                    <option value="">Select skill level ...</option>
                    <option value="Junior">Junior</option>
                    <option value="Medior">Medior</option>
                    <option value="Senior">Senior</option>
                    <option value="Mentor">Mentor</option>
                </select>
            </div>
            <div class="form-group">
                <label for="skill_weight${counter}">Skill Weight (Optional)</label>
                <input type="number" id="skill_weight${counter}" name="skill_weight${counter}" placeholder="Enter skill weight ..." class="form-control">
                <span class="error-message"></span>
            </div>
            <button class="remove-row" data-row="#row${counter}">Remove</button>
        </div>`);
        newInputRow.find('.remove-row').click(function(e){
            e.preventDefault();
            $($(this).data('row')).remove();
        });
        enableAutocomplete(newInputRow.find('input[name="option_skill'+counter+'"]'));
        $("#input-container").append(newInputRow);
        counter++;
    });
    // Add error handling for the option_skill fields
    $(document).on('blur', 'input[name^="option_skill"]', function() {
        var enteredSkill = $(this).val();
        var isValid = enteredSkill === "" || availableOptions.includes(enteredSkill);
        $(this).toggleClass('error', !isValid);
        $(this).siblings('.error-message').text(isValid ? "" : "Invalid skill name");
    });
    // Add error handling for the skill_weight fields
    $(document).on('blur', 'input[name^="skill_weight"]', function() {
    var skillWeight = parseFloat($(this).val());
    if (skillWeight < 0) {
        $(this).addClass('error');
        $(this).siblings('.error-message').text("Weight cannot be negative.");
    } else if (skillWeight == 0) {
        $(this).addClass('error');
        $(this).siblings('.error-message').text("Weight cannot be 0.");
    } else {
        $(this).removeClass('error');
        $(this).siblings('.error-message').text("");
    }
});
    // Handle the color change of buttons when the selection changes
    $('input[name="looking-for"]').change(function() {
        if ($(this).val() === 'Volunteer') {
            $(this).parent().addClass('btn-selected').removeClass('btn-unselected');
            $('input[name="looking-for"][value="Mentor"]').parent().addClass('btn-unselected').removeClass('btn-selected');
        } else {
            $(this).parent().addClass('btn-selected').removeClass('btn-unselected');
            $('input[name="looking-for"][value="Volunteer"]').parent().addClass('btn-unselected').removeClass('btn-selected');
        }
    });
    $('input[name="looking-for"]:checked').change();
});