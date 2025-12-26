console.log("main.js loaded ✅");

// Global variables (Backup)
let currentSource = "animexin";
let globalAnimeTitle = "Anime"; 
let globalEpisodeNum = "";

$(document).ready(function () {
  changeSource('animexin');

  // 1. CAPTURE TITLE (Click on Anime Card)
  // We listen on the whole article card to ensure we catch the click
  $("body").on("click", "article.bs, article.bs a", function() {
      let card = $(this).closest("article.bs");
      let title = card.find(".tt, .eggtitle, .entry-title, h2, h4").text();
      if (title) {
          // Remove "Episode X" garbage if present
          globalAnimeTitle = title.replace(/Episode\s+\d+.*/i, "").trim();
          console.log("🎯 Title Captured:", globalAnimeTitle);
      }
  });

  // 2. CAPTURE EPISODE (Click on Episode List)
  $("body").on("click", ".eplister li", function() {
      let num = $(this).find(".epl-num").text() || $(this).text();
      globalEpisodeNum = num.trim();
      console.log("🎯 Episode Captured:", globalEpisodeNum);
  });

  // Search Form
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
    // Try to grab title from the new page content immediately
    let t = $("#episodes h1").text() || $("#episodes .entry-title").text();
    if(t) globalAnimeTitle = t.trim();
    $("html, body").animate({ scrollTop: $("#episodes").offset().top - 30 }, 600);
  });
}

function selectEpisode(ep_token) {
  $.post("/get_servers", { episode_token: ep_token }, function (data) {
    $("#serverSelection").html(data).show();
    $("#subtitleSelection, #stream").hide();
    $("html, body").animate({ scrollTop: $("#serverSelection").offset().top - 20 }, 600);
  });
}

function selectServer(ep_token, server_value) {
  $.post("/get_subtitles", { episode_token: ep_token, server: server_value }, function (data) {
    $("#subtitleSelection").html(data).show();
    $("#stream").hide();
    $("html, body").animate({ scrollTop: $("#subtitleSelection").offset().top - 20 }, 600);
  });
}

// ✅ FIX IS HERE: Use document.activeElement
function selectSubtitle(ep_token, server_value, sub_value) {
  
  // 1. Get the button that was just clicked
  let btn = $(document.activeElement);
  let btnText = btn.text().trim();
  
  // If activeElement failed (rare), fallback to globals
  let finalTitle = globalAnimeTitle;
  let finalEp = globalEpisodeNum;

  console.log("🖱️ Clicked Button Text:", btnText);

  // 2. Parse Title (Text between " - " and " Episode")
  // Example: "Ep 4 - Wealth and Wonder Episode 4 Subtitle"
  let titleMatch = btnText.match(/-\s*(.*?)\s*Episode/i);
  if (titleMatch && titleMatch[1]) {
      finalTitle = titleMatch[1].trim();
  }

  // 3. Parse Episode (Text after "Ep ")
  let epMatch = btnText.match(/Ep\s*(\d+)/i);
  if (epMatch && epMatch[1]) {
      finalEp = epMatch[1];
  }

  // Fallback cleanup
  if (!finalTitle || finalTitle === "Anime") finalTitle = "Anime";

  console.log("🚀 Downloading -> Title:", finalTitle, "| Ep:", finalEp);

  $.post('/stream', { 
      episode_token: ep_token,  
      server: server_value,     
      subtitle: sub_value,
      title: finalTitle,
      episode: finalEp
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
