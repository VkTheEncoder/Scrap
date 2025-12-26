console.log("main.js loaded ✅");

// Global variables to track state
let currentSource = "animexin";
let globalAnimeTitle = ""; 
let globalEpisodeNum = "";

$(document).ready(function () {
  changeSource('animexin');

  // ===============================
  // 1. CAPTURE EPISODE NUMBER (CRITICAL FIX)
  // ===============================
  // Use 'body' delegation to ensure it works even after AJAX loads
  $("body").on("click", ".eplister ul li a, .eplister ul li", function() {
      // 1. Try to find the specific number class
      let num = $(this).find(".epl-num").text();
      
      // 2. If not found, just get the text of the link itself
      if (!num) num = $(this).text();
      
      // 3. Clean it up
      globalEpisodeNum = num.trim();
      console.log("✅ Captured Episode Click:", globalEpisodeNum);
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
    globalAnimeTitle = ""; 
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
    
    // ✅ FIX: Grab the title from the LOADED CONTENT, not the page header
    // We look specifically inside the #episodes container
    setTimeout(function() {
        let titleCandidate = $("#episodes h1").text() || $("#episodes .entry-title").text();
        if(titleCandidate) {
            globalAnimeTitle = titleCandidate.trim();
            console.log("✅ Captured Title:", globalAnimeTitle);
        } else {
             console.warn("⚠️ Could not find title inside #episodes");
        }
    }, 100);

    $("html, body").animate({ scrollTop: $("#episodes").offset().top - 30 }, 600);
  });
}

// 2. Select Episode
function selectEpisode(ep_token) {
  if (!ep_token) return;
  // Note: globalEpisodeNum is already captured by the 'click' listener at top of file
  
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

  // Fallback: If title is missing, try one last desperate grab from the page
  if (!finalTitle || finalTitle === "Search Anime") {
       finalTitle = $("#episodes h1").text().trim();
  }
  // Fallback: Default to "Anime" if still failing
  if (!finalTitle) finalTitle = "Anime";

  console.log("🚀 Requesting Stream -> Title:", finalTitle, "| Ep:", finalEp);

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
