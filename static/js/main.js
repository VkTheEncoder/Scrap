// ===============================
// Handle Search Form Submit
// ===============================
$("#searchForm").on("submit", function(e) {
    e.preventDefault();

    // Collect values from form
    let query = $("#query").val();
    let server = $("#server").val();
    let subtitle = $("#subtitle").val();

    if (!query) {
        alert("Please enter an anime name or URL");
        return;
    }

    // Send AJAX request
    $.post("/search", {
        query: query,
        server: server,
        subtitle: subtitle
    }, function(data) {
        // Inject results
        $("#results").html(data).show();
        $("#episodes, #stream").hide();
    }).fail(function() {
        alert("Error while searching. Please try again.");
    });
});


// ===============================
// Select Anime -> Load Episodes
// ===============================
function selectAnime(id) {
    $.post("/episodes", { anime_id: id }, function(data) {
        $("#episodes").html(data).show();
        $("#stream").hide();
    }).fail(function() {
        alert("Error loading episodes.");
    });
}


// ===============================
// Select Episode -> Load Stream
// ===============================
function selectEpisode(anime_id, ep) {
    if (!ep) {
        alert("Please enter/select an episode.");
        return;
    }

    $.post("/stream", {
        anime_id: anime_id,
        episode: ep,
        subtitle: $("#subtitle").val()
    }, function(data) {
        $("#stream").html(data).show();
    }).fail(function() {
        alert("Error loading stream.");
    });
}
