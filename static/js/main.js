console.log("main.js loaded ✅");

// Global variables to memorize the name
let currentSource = "animexin";
let globalAnimeTitle = "Anime"; 
let globalEpisodeNum = "";

$(document).ready(function () {
  changeSource('animexin');

  // ============================================================
  // 1. CAPTURE DATA FROM THE EPISODE BUTTON (The logic you asked for)
  // ============================================================
  // We use the class ".ep-btn" because your HTML file uses it for every episode

  // ===============================
  // Search Form
  // ===============================
  $("#searchForm").on("submit", function (e) {
    e.preventDefault();
    const query = $("#query").val().trim();
    if (!query) { alert("Please enter anime name."); return; }
    let searchRoute = (currentSource === "tca") ? "/search_tca" : "/search";

    $.post(searchRoute, { query: query }, function (data) {
      $("#results").html(data).show();
      $("#episodes, #serverSelection, #subtitleSelection, #stream").hide();
      $("#latest").hide();
      $("html, body").animate({ scrollTop: $("#results").offset().top - 30 }, 600);
    }).fail(function () { alert("Error searching."); });
  });
});

// Switch Source
function changeSource(source) {
    currentSource = source;
    // Reset Globals
    globalAnimeTitle = "Anime";
    globalEpisodeNum = "";
    
    if (source === 'animexin') {
        $("#btn-animexin").removeClass("btn-outline-primary").addClass("btn-primary");
        $("#btn-tca").removeClass("btn-primary").addClass("btn-outline-primary");
    } else {
        $("#btn-tca").removeClass("btn-outline-primary").addClass("btn-primary");
        $("#btn-animexin").removeClass("btn-primary").addClass("btn-outline-primary");
    }
    $("#results, #episodes, #stream").hide();
    $("#latest").show().html("<p class='text-center'>Loading latest releases...</p>");
    loadLatest(1); 
}

function loadLatest(page) {
  let route = (currentSource === "tca") ? "/latest_tca" : "/latest";
  $.get(route, { page: page || 1 }, function (html) { $("#latest").html(html).show(); });
}

function loadMoreLatest(btn) {
  const $btn = $(btn);
  $.get("/latest", { page: $btn.data("next") }, function (html) {
    $("#latestList").append($(html).find("#latestList").html());
    let next = $(html).find("#latestNextBtn").data("next");
    next ? $btn.data("next", next).prop("disabled", false).text("Next →") : $btn.remove();
  });
}

// ===============================
// CORE FUNCTIONS
// ===============================

function selectAnime(id) {
  $("#results").hide(); $("#latest").hide();
  $.post("/episodes", { anime_id: id }, function (data) {
    $("#episodes").html(data).show();
    $("#serverSelection, #subtitleSelection, #stream").hide();
    $("html, body").animate({ scrollTop: $("#episodes").offset().top - 30 }, 600);
  });
}

// NOTE: This function is triggered by your HTML onclick="selectEpisode(...)"
// We don't need to change it because our new listener above captures the data BEFORE this runs.
function selectEpisode(ep_token, buttonElement) {
  // Read the title and episode number directly from the button.
  if (buttonElement) {
    globalAnimeTitle = (
      buttonElement.dataset.title || "Anime"
    ).trim();

    globalEpisodeNum = (
      buttonElement.dataset.num || ""
    ).trim();
  }

  console.log(
    "Selected anime:",
    globalAnimeTitle,
    "| Episode:",
    globalEpisodeNum
  );

  $.post(
    "/get_servers",
    { episode_token: ep_token },
    function (data) {
      $("#serverSelection").html(data).show();
      $("#subtitleSelection, #stream").hide();

      $("html, body").animate({
        scrollTop: $("#serverSelection").offset().top - 20
      }, 600);
    }
  );
}
function selectServer(ep_token, server_value) {
  $.post("/get_subtitles", { episode_token: ep_token, server: server_value }, function (data) {
    $("#subtitleSelection").html(data).show();
    $("#stream").hide();
    $("html, body").animate({ scrollTop: $("#subtitleSelection").offset().top - 20 }, 600);
  });
}

function selectSubtitle(ep_token, server_value, sub_value) {
  
  // Use the global variables we captured earlier when the user clicked the Episode Button
  let finalTitle = globalAnimeTitle;
  let finalEp = globalEpisodeNum;

  // Safety Fallback
  if (!finalTitle) finalTitle = "Anime";

  console.log("🚀 Sending to Server -> Title:", finalTitle, "| Ep:", finalEp);

  $.post('/stream', { 
      episode_token: ep_token,  
      server: server_value,     
      subtitle: sub_value,
      title: finalTitle,        // <--- Sending the parsed name
      episode: finalEp          // <--- Sending the parsed episode
  }, function(data) {
      $("#stream").html(data).show();
      $("html, body").animate({ scrollTop: $("#stream").offset().top - 20 }, 600);
  }).fail(function () {
    alert("Error loading stream.");
  });
}

function processAllEpisodes(anime_id) {
  $.post("/process_all", { anime_id: anime_id }, function (data) {
    $("#stream").html(data).show();
    $("#results, #episodes, #serverSelection, #subtitleSelection").hide();
    $("html, body").animate({ scrollTop: $("#stream").offset().top - 20 }, 600);
  });
}
