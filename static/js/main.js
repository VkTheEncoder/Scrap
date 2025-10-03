console.log("main.js loaded ✅");

$(document).ready(function() {
    // ===============================
    // Handle Search Form Submit
    // ===============================
    $("#searchForm").on("submit", function(e) {
        e.preventDefault();
        console.log("Search form submitted via AJAX ✅");

        $.post("/search", {
            query: $("#query").val(),
            server: $("#server").val(),
            subtitle: $("#subtitle").val()
        }, function(data) {
            $("#results").html(data).show();
            $("#episodes, #stream").hide();
        }).fail(function() {
            alert("Error while searching. Please try again.");
        });
    });
});

// ===============================
// Select Anime -> Load Episodes
// ===============================
function selectAnime(id) {
    console.log("Anime selected:", id);
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
    console.log("Episode selected:", ep);

    $.post("/stream", {
        anime_id: anime_id,
        episode: ep,
        subtitle: $("#subtitle").val(),
        server: $("#server").val()
    }, function(data) {
        $("#stream").html(data).show();
    }).fail(function() {
        alert("Error loading stream.");
    });
}
