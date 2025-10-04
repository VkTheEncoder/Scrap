console.log("main.js loaded ✅");

$(document).ready(function() {
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

// Anime card -> load episodes
function selectAnime(id) {
  console.log("Anime selected:", id);
  $.post("/episodes", { anime_id: id }, function(data) {
    $("#episodes").html(data).show();
    $("#stream").hide();
  }).fail(function() {
    alert("Error loading episodes.");
  });
}

// Episode -> load stream (IMPORTANT: now expects an EPISODE TOKEN)
function selectEpisode(ep_token) {
  if (!ep_token) { alert("Please choose an episode."); return; }
  console.log("Episode selected:", ep_token);

  $.post("/stream", {
    episode_token: ep_token,                  // <- token of the episode page
    subtitle: $("#subtitle").val(),
    server: $("#server").val()
  }, function(data) {
    $("#stream").html(data).show();
  }).fail(function() {
    alert("Error loading stream.");
  });
}
