// ===============================
// Handle Search Form Submit
// ===============================
$("#searchForm").on("submit", function(e) {
    e.preventDefault();
    $.post("/search", {
        query: $("#query").val(),
        server: $("#server").val(),
        subtitle: $("#subtitle").val()
    }, function(data) {
        $("#results").html(data).show();
        $("#episodes, #stream").hide();
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
