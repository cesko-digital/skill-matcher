$(document).ready(function() {
    let displayed_rows = 0;
    let increment = 10;
    let rows = $("tr").not("thead tr");
    let total_rows = rows.length;

    function showMoreRows() {
        for (let i = displayed_rows; i < displayed_rows + increment; i++) {
            $(rows[i]).show();
        }
        displayed_rows += increment;

        if (displayed_rows >= total_rows) {
            $("#show_more").hide();
        }
    }

    $("#show_more").click(showMoreRows);

    // Hide all rows initially
    rows.hide();

    // Show initial 10 rows
    showMoreRows();

    // Retrieve selected rows on button click
    $("#retrieve_selected").click(function() {
        let selectedRows = [];

        $("input.email-checkbox:checked").each(function() {
            let row = $(this).closest("tr");
            let rowData = {
                "Name": row.find("td:eq(1)").text(),
                "Email": row.find("td:eq(2)").text(),
                // Add additional columns as needed
            };
            selectedRows.push(rowData);
        });

        // Send the selected rows to the server
        $.ajax({
            type: "POST",
            url: "/prep_email",
            data: JSON.stringify(selectedRows),
            contentType: "application/json",
            success: function(response) {
console.log("Selected rows sent to the server successfully.");
// Redirect to the url returned from the server
window.open(response.url, "_blank");
},
            error: function(error) {
                console.log("Error sending selected rows to the server.");
                console.log(error);
            }
        });
    });
});