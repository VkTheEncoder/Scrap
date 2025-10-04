console.log("main.js loaded ✅");

$(document).ready(function () {
  // ===============================
  // Handle Search Form Submit
  // ===============================
  $("#searchForm").on("submit", function (e) {
    e.preventDefault();
    const query = $("#query").val().trim();
    if (!query) {
      alert("Please enter anime name.");
      return;
    }

    console.log("Searching for:", query);
    $.post("/search", { query: query }, function (data) {
      $("#results").html(data).show();
      $("#episodes, #serverSelection, #subtitleSelection, #stream").hide();
    }).fail(function () {
      alert("Error while searching. Please try again.");
    });
  });
});

// ===============================
// When user selects an anime → load episodes
// ===============================
function selectAnime(id) {
  console.log("Anime selected:", id);
  $("#results").hide();  // 🔹 Hide search results when an anime is selected

  $.post("/episodes", { anime_id: id }, function(data) {
    $("#episodes").html(data).show();
    $("#stream").hide();
  }).fail(function() {
    alert("Error loading episodes.");
  });
}

// ===============================
// When user selects an episode → load available servers
// ===============================
function selectEpisode(ep_token) {
  if (!ep_token) {
    alert("Please choose an episode.");
    return;
  }

  console.log("Episode selected:", ep_token);

  $.post("/stream", {
    episode_token: ep_token,
  }, function (data) {
    $("#stream").html(data).show();

    // ✅ Auto-scroll smoothly to the stream section
    $("html, body").animate({
      scrollTop: $("#stream").offset().top - 20
    }, 600);
  }).fail(function () {
    alert("Error loading stream.");
  });
}

// ===============================
// When user selects a server → load available subtitles
// ===============================
function selectServer(ep_token, server_value) {
  console.log("Server selected for:", ep_token);

  $.post("/get_subtitles", {
    episode_token: ep_token,
    server: server_value
  }, function (data) {
    $("#subtitleSelection").html(data).show();
    $("#stream").hide();
  }).fail(function () {
    alert("Error loading subtitles.");
  });
}

// ===============================
// When user selects subtitle → load stream player
// ===============================
function selectSubtitle(ep_token, server_value, sub_value) {
  console.log("Subtitle selected:", sub_value);

  $.post("/stream", {
    episode_token: ep_token,
    server: server_value,
    subtitle: sub_value
  }, function (data) {
    $("#stream").html(data).show();
  }).fail(function () {
    alert("Error loading stream.");
  });
}



function processAllEpisodes(anime_id) {
  console.log("Processing all episodes:", anime_id);
  $.post("/process_all", { anime_id: anime_id }, function (data) {
    $("#stream").html(data).show();
    $("#results, #episodes").hide();
  }).fail(function () {
    alert("Error processing all episodes.");
  });
}

