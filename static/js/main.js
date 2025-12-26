console.log("main.js loaded ✅");

// Global variable to track active source (default: animexin)
let currentSource = "animexin";

$(document).ready(function () {
  // Load default source on startup
  changeSource('animexin');

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

    // Decide which route to hit based on currentSource
    let searchRoute = "/search"; // default animexin
    if (currentSource === "tca") {
        searchRoute = "/search_tca";
    }

    console.log(`Searching on ${currentSource} for:`, query);
    
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
    console.log("Switched source to:", source);

    // Update UI Buttons
    if (source === 'animexin') {
        $("#btn-animexin").removeClass("btn-outline-primary").addClass("btn-primary");
        $("#btn-tca").removeClass("btn-primary").addClass("btn-outline-primary");
    } else {
        $("#btn-tca").removeClass("btn-outline-primary").addClass("btn-primary");
        $("#btn-animexin").removeClass("btn-primary").addClass("btn-outline-primary");
    }

    // Clear previous views
    $("#results, #episodes, #stream").hide();
    $("#latest").show().html("<p class='text-center'>Loading latest releases...</p>");

    // Load appropriate Latest
    loadLatest(1); 
}

// ===============================
// LOAD LATEST (Dynamic)
// ===============================
function loadLatest(page) {
  let route = "/latest"; // default
  if (currentSource === "tca") {
      route = "/latest_tca";
  }

  $.get(route, { page: page || 1 }, function (html) {
    $("#latest").html(html).show();
  }).fail(function () {
    console.warn("Failed to load Latest Release.");
    $("#latest").html("<p>Error loading content.</p>");
  });
}

// Append next page results while keeping the same click behavior
function loadMoreLatest(btn) {
  const $btn = $(btn);
  const next = $btn.data("next");
  if (!next) return;

  $btn.prop("disabled", true).text("Loading…");

  $.get("/latest", { page: next }, function (html) {
    const $html = $(html);
    const itemsHtml =
      $html.find("#latestList").html() ||
      $html.find(".results-list").html() ||
      "";

    // append new cards
    $("#latestList").append(itemsHtml);

    // update or remove Next button
    const $nextBtn = $html.find("#latestNextBtn");
    if ($nextBtn.length) {
      $btn.data("next", $nextBtn.data("next")).prop("disabled", false).text("Next →");
    } else {
      $btn.remove();
    }
  }).fail(function () {
    alert("Couldn't load more releases.");
    $btn.prop("disabled", false).text("Next →");
  });
}

/* =========================================================
   EXISTING FLOW: SEARCH → EPISODES → SERVERS → SUBTITLES → STREAM
   ========================================================= */

// When user selects an anime → load episodes
function selectAnime(id) {
  console.log("Anime selected:", id);
  $("#results").hide(); // hide search results
  $("#latest").hide();  // hide latest when going inside a show (optional)

  $.post("/episodes", { anime_id: id }, function (data) {
    $("#episodes").html(data).show();
    $("#serverSelection, #subtitleSelection, #stream").hide();

    // Smooth scroll to episodes
    $("html, body").animate({
      scrollTop: $("#episodes").offset().top - 30
    }, 600);
  }).fail(function () {
    alert("Error loading episodes.");
  });
}

// When user selects an episode → load available servers
function selectEpisode(ep_token) {
  if (!ep_token) {
    alert("Invalid episode token.");
    return;
  }
  console.log("Episode selected:", ep_token);

  $.post("/get_servers", { episode_token: ep_token }, function (data) {
    $("#serverSelection").html(data).show();
    $("#subtitleSelection, #stream").hide();

    // ✅ Auto-scroll to server selection
    $("html, body").animate({
      scrollTop: $("#serverSelection").offset().top - 20
    }, 600);
  }).fail(function () {
    alert("Error loading available servers.");
  });
}

// When user selects a server → load available subtitles
function selectServer(ep_token, server_value) {
  console.log("Server selected for:", ep_token, "| Server:", server_value);

  $.post("/get_subtitles", {
    episode_token: ep_token,
    server: server_value
  }, function (data) {
    $("#subtitleSelection").html(data).show();
    $("#stream").hide();

    // ✅ Auto-scroll to subtitle section
    $("html, body").animate({
      scrollTop: $("#subtitleSelection").offset().top - 20
    }, 600);
  }).fail(function () {
    alert("Error loading subtitles.");
  });
}

// ===============================
// ✅ FIX IS HERE: SELECT SUBTITLE
// ===============================
function selectSubtitle(ep_token, server_value, sub_value) {
  console.log("Subtitle selected:", sub_value);

  // 1. Try to get the Anime Name (usually in an h2 tag at the top of the page)
  var animeName = $("h2").first().text().trim() || "Anime";

  // 2. Try to get the Episode Number (optional fallback)
  var episodeNum = ""; 

  // 3. Send Request to Python (WITH title and episode)
  $.post('/stream', { 
      episode_token: ep_token,  // Use the correct variable passed to function
      server: server_value,     // Use the correct variable passed to function
      subtitle: sub_value,
      title: animeName,         // Sending Title
      episode: episodeNum       // Sending Episode
  }, function(data) {
      // Load the player
      $("#stream").html(data).show();
      
      // ✅ Smooth scroll to stream section
      $("html, body").animate({
        scrollTop: $("#stream").offset().top - 20
      }, 600);

  }).fail(function () {
    alert("Error loading stream.");
  });
}

// Process all episodes (optional feature)
function processAllEpisodes(anime_id) {
  console.log("Processing all episodes:", anime_id);

  $.post("/process_all", { anime_id: anime_id }, function (data) {
    $("#stream").html(data).show();
    $("#results, #episodes, #serverSelection, #subtitleSelection").hide();

    $("html, body").animate({
      scrollTop: $("#stream").offset().top - 20
    }, 600);
  }).fail(function () {
    alert("Error processing all episodes.");
  });
}
