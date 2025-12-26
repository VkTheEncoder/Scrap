console.log("main.js loaded ✅");

// Global variables to track state
let currentSource = "animexin";
let globalAnimeTitle = "Anime";
let globalEpisodeNum = "";

$(document).ready(function () {
  changeSource('animexin');

  // ===============================
  // 1. CAPTURE EPISODE NUMBER ON CLICK
  // ===============================
  // This listens for clicks on any episode button to save the number
  $(document).on("click", ".eplister ul li a, .eplister li a", function() {
      // Try to find the number inside the clicked element
      let num = $(this).find(".epl-num").text() || $(this).text();
      globalEpisodeNum = num.trim();
      console.log("Captured Episode:", globalEpisodeNum);
  });

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

    let searchRoute = (currentSource === "tca") ? "/search_tca" : "/search";

    $.post(searchRoute, { query: query }, function (data) {
      $("#results").html(data).show();
      $("#episodes, #serverSelection, #subtitleSelection, #stream").hide();
      $("#latest").hide();
      $("html, body").animate({ scrollTop: $("#results").offset().top - 30 }, 600);
    }).fail(function () {
      alert("Error while searching.");
    });
  });
});

// ===============================
// SWITCH SOURCE FUNCTION
// ===============================
function changeSource(source) {
    currentSource = source;
    // Reset Globals
    globalAnimeTitle = "Anime";
    globalEpisodeNum = "";
    
    // UI Updates
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

// ===============================
// LOAD LATEST
// ===============================
function loadLatest(page) {
  let route = (currentSource === "tca") ? "/latest_tca" : "/latest";
  $.get(route, { page: page || 1 }, function (html) {
    $("#latest").html(html).show();
  });
}

// Load More Button
function loadMoreLatest(btn) {
  const $btn = $(btn);
  const next = $btn.data("next");
  if (!next) return;

  $btn.prop("disabled", true).text("Loading…");
  $.get("/latest", { page: next }, function (html) {
    const $html = $(html);
    const itemsHtml = $html.find("#latestList").html() || $html.find(".results-list").html() || "";
    $("#latestList").append(itemsHtml);
    
    const $nextBtn = $html.find("#latestNextBtn");
    if ($nextBtn.length) {
      $btn.data("next", $nextBtn.data("next")).prop("disabled", false).text("Next →");
    } else {
      $btn.remove();
    }
  });
}

// ===============================
// CORE FUNCTIONS
// ===============================

// 1. Select Anime
function selectAnime(id) {
  $("#results").hide(); 
  $("#latest").hide();

  $.post("/episodes", { anime_id: id }, function (data) {
    $("#episodes").html(data).show();
    $("#serverSelection, #subtitleSelection, #stream").hide();
    
    // FIX: Grab the title immediately after loading the episodes
    // We look for .entry-title (standard) or just the first H1 inside the episodes container
    setTimeout(function() {
        let title = $("#episodes .entry-title").text().trim() || $("#episodes h1").text().trim();
        if(title) {
            globalAnimeTitle = title;
            console.log("Captured Title:", globalAnimeTitle);
        }
    }, 100);

    $("html, body").animate({ scrollTop: $("#episodes").offset().top - 30 }, 600);
  });
}

// 2. Select Episode
function selectEpisode(ep_token) {
  if (!ep_token) return;
  
  $.post("/get_servers", { episode_token: ep_token }, function (data) {
    $("#serverSelection").html(data).show();
    $("#subtitleSelection, #stream").hide();
    $("html, body").animate({ scrollTop: $("#serverSelection").offset().top - 20 }, 600);
  });
}

// 3. Select Server
function selectServer(ep_token, server_value) {
  $.post("/get_subtitles", {
    episode_token: ep_token,
    server: server_value
  }, function (data) {
    $("#subtitleSelection").html(data).show();
    $("#stream").hide();
    $("html, body").animate({ scrollTop: $("#subtitleSelection").offset().top - 20 }, 600);
  });
}

// 4. Select Subtitle (FINAL STEP)
function selectSubtitle(ep_token, server_value, sub_value) {
  
  // Use the captured globals!
  let finalTitle = globalAnimeTitle;
  let finalEp = globalEpisodeNum;

  // Fallback: If global is empty, try to grab from DOM again
  if (!finalTitle || finalTitle === "Anime") {
       finalTitle = $(".entry-title").first().text().trim() || $("h1").first().text().trim();
  }

  console.log("Requesting Stream with:", finalTitle, finalEp);

  $.post('/stream', { 
      episode_token: ep_token,  
      server: server_value,     
      subtitle: sub_value,
      title: finalTitle,        // <--- Sending Correct Title
      episode: finalEp          // <--- Sending Correct Episode
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
