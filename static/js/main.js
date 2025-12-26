console.log("main.js loaded ✅");

// Global variables (Fallback)
let currentSource = "animexin";
let globalAnimeTitle = "Anime"; 
let globalEpisodeNum = "";

$(document).ready(function () {
  changeSource('animexin');

  // Capture Title/Episode from clicks (Fallback method)
  $("body").on("click", "article.bs a", function() {
      let title = $(this).closest("article.bs").find(".tt, .eggtitle, .entry-title, h2, h4").text();
      if (title) globalAnimeTitle = title.replace(/Episode\s+\d+.*/i, "").trim();
  });

  $("body").on("click", ".eplister li", function() {
      let num = $(this).find(".epl-num").text() || $(this).text();
      globalEpisodeNum = num.trim();
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

// Load Latest
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
    // Try to grab title from the new page content
    let t = $("#episodes h1").text();
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

// ✅ FIX IS HERE: Parse the name directly from the button you click
function selectSubtitle(ep_token, server_value, sub_value) {
  
  // 1. Get the text of the clicked button
  // Example: "Ep 4 - Wealth and Wonder Episode 4 Subtitle"
  let btnText = $(this).text().trim();
  
  let finalTitle = globalAnimeTitle;
  let finalEp = globalEpisodeNum;

  // 2. Try to extract Title from button (Regex: Text between " - " and " Episode")
  let titleMatch = btnText.match(/-\s*(.*?)\s*Episode/i);
  if (titleMatch && titleMatch[1]) {
      finalTitle = titleMatch[1].trim();
      console.log("✅ Found Title in Button:", finalTitle);
  }

  // 3. Try to extract Episode from button (Regex: "Ep 4")
  let epMatch = btnText.match(/Ep\s*(\d+)/i);
  if (epMatch && epMatch[1]) {
      finalEp = epMatch[1];
      console.log("✅ Found Ep in Button:", finalEp);
  }

  // Fallback: If button text didn't help, stick to defaults
  if (!finalTitle || finalTitle === "Anime") finalTitle = "Anime";

  console.log("🚀 Downloading ->", finalTitle, finalEp);

  $.post('/stream', { 
      episode_token: ep_token,  
      server: server_value,     
      subtitle: sub_value,
      title: finalTitle,        // Send Parsed Title
      episode: finalEp          // Send Parsed Episode
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
