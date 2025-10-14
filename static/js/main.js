console.log("main.js loaded ✅");

$(document).ready(function () {
  // ===============================
  // Load Latest Release (home cards)
  // ===============================
  loadLatest(1); // first page on load

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

      // hide latest section while user is in search flow (optional)
      $("#latest").hide();

      // Smooth scroll to results
      $("html, body").animate({
        scrollTop: $("#results").offset().top - 30
      }, 600);
    }).fail(function () {
      alert("Error while searching. Please try again.");
    });
  });
});

/* =========================================================
   LATEST RELEASE HELPERS
   ========================================================= */

// Load a page of latest releases into #latest
function loadLatest(page) {
  $.get("/latest", { page: page || 1 }, function (html) {
    $("#latest").html(html).show();
  }).fail(function () {
    console.warn("Failed to load Latest Release.");
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

// When user selects subtitle → load stream info
function selectSubtitle(ep_token, server_value, sub_value) {
  console.log("Subtitle selected:", sub_value);

  $.post("/stream", {
    episode_token: ep_token,
    server: server_value,
    subtitle: sub_value
  }, function (data) {
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
