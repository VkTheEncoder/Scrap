console.log("main.js loaded: v20260716-json-subtitle-v2");

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
      $("#results").html("<p class='text-center' style='color:red;'>Error searching. Please try again.</p>");
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
    $("#episodes").html("<p class='text-center' style='color:red;'>Error loading episodes.</p>");
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
    $("#serverSelection").html("<p class='text-center' style='color:red;'>Error loading servers.</p>");
  });
}

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

  // Show loading immediately so user knows the click was registered
  $("#subtitleSelection").html("<p class='text-center'>⏳ Loading...</p>").show();
  $("#stream").hide();
  $("html, body").animate({ scrollTop: $("#subtitleSelection").offset().top - 20 }, 300);

  // /get_subtitles now returns JSON
  $.post("/get_subtitles", context, function (json) {
    if (json.subs && json.subs.length > 0) {
      // Has subtitles — show selection UI
      var html = "<h3>Select Subtitle</h3>";
      json.subs.forEach(function (sub) {
        html += '<button type="button"' +
          ' data-episode-token="' + escAttr(json.ep_token) + '"' +
          ' data-server="' + escAttr(json.server_value) + '"' +
          ' data-subtitle="' + escAttr(sub.lang) + '"' +
          ' data-title="' + escAttr(json.anime_title) + '"' +
          ' data-episode="' + escAttr(json.episode_num) + '"' +
          ' onclick="selectSubtitle(this)">' +
          escHtml(sub.lang) + ' (' + escHtml(sub.name) + ')' +
          '</button> ';
      });
      // Always add a Skip button
      html += '<br><br><button type="button"' +
        ' data-episode-token="' + escAttr(json.ep_token) + '"' +
        ' data-server="' + escAttr(json.server_value) + '"' +
        ' data-subtitle=""' +
        ' data-title="' + escAttr(json.anime_title) + '"' +
        ' data-episode="' + escAttr(json.episode_num) + '"' +
        ' onclick="selectSubtitle(this)">▶ Skip / No Subtitle</button>';
      $("#subtitleSelection").html(html);
    } else {
      // No subtitles found — skip straight to stream
      console.log("No subtitles found, going directly to stream.");
      $("#subtitleSelection").hide();
      loadStream({
        episode_token: json.ep_token,
        server: json.server_value,
        subtitle: "",
        title: json.anime_title,
        episode: json.episode_num
      });
    }
  }, "json").fail(function (xhr) {
    console.error("get_subtitles failed:", xhr.status, xhr.responseText);
    $("#subtitleSelection").html("<p class='text-center' style='color:red;'>Error loading subtitles. Trying stream directly...</p>");
    // Fall through to stream anyway
    setTimeout(function () {
      loadStream({
        episode_token: context.episode_token,
        server: context.server,
        subtitle: "",
        title: context.title,
        episode: context.episode
      });
    }, 1500);
  });
}

function selectSubtitle(buttonElement) {
  if (!buttonElement) {
    alert("Subtitle context is missing. Reload the page and try again.");
    return;
  }

  const data = buttonElement.dataset;
  loadStream({
    episode_token: data.episodeToken || "",
    server: data.server || "",
    subtitle: data.subtitle || "",
    title: data.title || "Anime",
    episode: data.episode || ""
  });
}

function loadStream(context) {
  console.log("STREAM CONTEXT:", context);

  $("#stream").html("<p class='text-center'>⏳ Loading stream...</p>").show();
  $("html, body").animate({ scrollTop: $("#stream").offset().top - 20 }, 300);

  $.post("/stream", context, function (html) {
    $("#stream").html(html);
  }).fail(function () {
    $("#stream").html("<p class='text-center' style='color:red;'>Error loading stream.</p>");
  });
}

function processAllEpisodes(animeId) {
  $("#stream").html("<p class='text-center'>⏳ Processing all episodes...</p>").show();
  $("#results, #episodes, #serverSelection, #subtitleSelection").hide();
  $("html, body").animate({ scrollTop: $("#stream").offset().top - 20 }, 600);

  $.post("/process_all", { anime_id: animeId }, function (data) {
    $("#stream").html(data);
  }).fail(function () {
    $("#stream").html("<p class='text-center' style='color:red;'>Error processing episodes.</p>");
  });
}

// Utility: escape HTML attribute characters
function escAttr(str) {
  return String(str || "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/'/g, "&#39;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Utility: escape HTML content
function escHtml(str) {
  return String(str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
