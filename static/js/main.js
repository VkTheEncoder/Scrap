console.log("main.js loaded: filename-context-v1");

let currentSource = "animexin";
let globalAnimeTitle = "Anime";
let globalEpisodeNum = "";

$(document).ready(function () {
  changeSource("animexin");

  $("#searchForm").on("submit", function (e) {
    e.preventDefault();
    const query = $("#query").val().trim();
    if (!query) {
      alert("Please enter anime name.");
      return;
    }

    const searchRoute = currentSource === "tca" ? "/search_tca" : "/search";
    
    $("#results").html("<p class='text-center'>Searching...</p>").show();
    $("#episodes, #serverSelection, #subtitleSelection, #stream").hide();
    $("#latest").hide();
    $("html, body").animate({ scrollTop: $("#results").offset().top - 30 }, 600);

    $.post(searchRoute, { query }, function (data) {
      $("#results").html(data);
    }).fail(function () {
      $("#results").html("<p class='text-center text-danger'>Error searching.</p>");
    });
  });
});

function changeSource(source) {
  currentSource = source;
  globalAnimeTitle = "Anime";
  globalEpisodeNum = "";

  if (source === "animexin") {
    $("#btn-animexin").removeClass("btn-outline-primary").addClass("btn-primary");
    $("#btn-tca").removeClass("btn-primary").addClass("btn-outline-primary");
  } else {
    $("#btn-tca").removeClass("btn-outline-primary").addClass("btn-primary");
    $("#btn-animexin").removeClass("btn-primary").addClass("btn-outline-primary");
  }

  $("#results, #episodes, #serverSelection, #subtitleSelection, #stream").hide();
  $("#latest").show().html("<p class='text-center'>Loading latest releases...</p>");
  loadLatest(1);
}

function loadLatest(page) {
  const route = currentSource === "tca" ? "/latest_tca" : "/latest";
  $.get(route, { page: page || 1 }, function (html) {
    $("#latest").html(html).show();
  });
}

function loadMoreLatest(btn) {
  const $btn = $(btn);
  const route = currentSource === "tca" ? "/latest_tca" : "/latest";
  $.get(route, { page: $btn.data("next") }, function (html) {
    $("#latestList").append($(html).find("#latestList").html());
    const next = $(html).find("#latestNextBtn").data("next");
    if (next) {
      $btn.data("next", next).prop("disabled", false).text("Next →");
    } else {
      $btn.remove();
    }
  });
}

function selectAnime(id) {
  $("#results, #latest").hide();
  
  $("#episodes").html("<p class='text-center'>Loading episodes...</p>").show();
  $("#serverSelection, #subtitleSelection, #stream").hide();
  $("html, body").animate({ scrollTop: $("#episodes").offset().top - 30 }, 600);

  $.post("/episodes", { anime_id: id }, function (data) {
    $("#episodes").html(data);
  }).fail(function () {
    $("#episodes").html("<p class='text-center text-danger'>Error loading episodes.</p>");
  });
}

function selectEpisode(epToken, buttonElement) {
  if (!buttonElement) {
    alert("Episode context is missing. Reload the page and try again.");
    return;
  }

  const animeTitle = (buttonElement.dataset.title || "Anime").trim();
  const episodeNum = (buttonElement.dataset.num || "").trim();

  globalAnimeTitle = animeTitle;
  globalEpisodeNum = episodeNum;

  console.log("EPISODE CONTEXT:", { animeTitle, episodeNum, epToken });

  $("#serverSelection").html("<p class='text-center'>Loading servers...</p>").show();
  $("#subtitleSelection, #stream").hide();
  $("html, body").animate({ scrollTop: $("#serverSelection").offset().top - 20 }, 600);

  $.post("/get_servers", {
    episode_token: epToken,
    title: animeTitle,
    episode: episodeNum
  }, function (data) {
    $("#serverSelection").html(data);
  }).fail(function () {
    $("#serverSelection").html("<p class='text-center text-danger'>Error loading servers.</p>");
  });
}

// This function was missing from the uploaded repository.
function selectServer(buttonElement) {
  if (!buttonElement) {
    alert("Server context is missing. Reload the page and try again.");
    return;
  }

  const data = buttonElement.dataset;
  const context = {
    episode_token: data.episodeToken || "",
    server: data.server || "",
    title: data.title || "Anime",
    episode: data.episode || ""
  };

  console.log("SERVER CONTEXT:", context);

  $("#subtitleSelection").html("<p class='text-center'>Loading subtitles...</p>").show();
  $("#stream").hide();
  $("html, body").animate({ scrollTop: $("#subtitleSelection").offset().top - 20 }, 600);

  $.post("/get_subtitles", context, function (html) {
    $("#subtitleSelection").html(html);
  }).fail(function () {
    $("#subtitleSelection").html("<p class='text-center text-danger'>Error loading subtitles.</p>");
  });
}

function selectSubtitle(buttonElement) {
  if (!buttonElement) {
    alert("Subtitle context is missing. Reload the page and try again.");
    return;
  }

  const data = buttonElement.dataset;
  const context = {
    episode_token: data.episodeToken || "",
    server: data.server || "",
    subtitle: data.subtitle || "",
    title: data.title || "Anime",
    episode: data.episode || ""
  };

  console.log("STREAM CONTEXT:", context);

  $("#stream").html("<p class='text-center'>Loading stream...</p>").show();
  $("html, body").animate({ scrollTop: $("#stream").offset().top - 20 }, 600);

  $.post("/stream", context, function (html) {
    $("#stream").html(html);
  }).fail(function () {
    $("#stream").html("<p class='text-center text-danger'>Error loading stream.</p>");
  });
}

function processAllEpisodes(animeId) {
  $("#stream").html("<p class='text-center'>Processing all episodes...</p>").show();
  $("#results, #episodes, #serverSelection, #subtitleSelection").hide();
  $("html, body").animate({ scrollTop: $("#stream").offset().top - 20 }, 600);

  $.post("/process_all", { anime_id: animeId }, function (data) {
    $("#stream").html(data);
  }).fail(function() {
    $("#stream").html("<p class='text-center text-danger'>Error processing episodes.</p>");
  });
}
