console.log("main.js loaded: restored-working-flow-v1");

let currentSource = "animexin";

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

    $.post(searchRoute, { query: query })
      .done(function (data) {
        $("#results").html(data).show();
        $("html, body").animate({ scrollTop: $("#results").offset().top - 30 }, 600);
      })
      .fail(function (xhr) {
        console.error("Search failed:", xhr.status, xhr.responseText);
        $("#results").html("<p class='text-center text-danger'>Error searching.</p>");
      });
  });
});

function changeSource(source) {
  currentSource = source;

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

  $.get(route, { page: page || 1 })
    .done(function (html) {
      $("#latest").html(html).show();
    })
    .fail(function (xhr) {
      console.error("Latest failed:", xhr.status, xhr.responseText);
      $("#latest").html("<p class='text-center text-danger'>Error loading latest releases.</p>");
    });
}

function loadMoreLatest(btn) {
  const $btn = $(btn);
  const route = currentSource === "tca" ? "/latest_tca" : "/latest";

  $.get(route, { page: $btn.data("next") })
    .done(function (html) {
      $("#latestList").append($(html).find("#latestList").html());
      const next = $(html).find("#latestNextBtn").data("next");

      if (next) {
        $btn.data("next", next).prop("disabled", false).text("Next →");
      } else {
        $btn.remove();
      }
    })
    .fail(function (xhr) {
      console.error("Load more failed:", xhr.status, xhr.responseText);
      $btn.prop("disabled", false).text("Try again");
    });
}

function selectAnime(id) {
  $("#results, #latest").hide();
  $("#episodes").html("<p class='text-center'>Loading episodes...</p>").show();
  $("#serverSelection, #subtitleSelection, #stream").hide();

  $.post("/episodes", { anime_id: id })
    .done(function (data) {
      $("#episodes").html(data).show();
      $("html, body").animate({ scrollTop: $("#episodes").offset().top - 30 }, 600);
    })
    .fail(function (xhr) {
      console.error("Episodes failed:", xhr.status, xhr.responseText);
      $("#episodes").html("<p class='text-center text-danger'>Error loading episodes.</p>");
    });
}

/* Restored original working request structure. */
function selectEpisode(epToken) {
  $("#serverSelection").html("<p class='text-center'>Loading servers...</p>").show();
  $("#subtitleSelection, #stream").hide();

  $.post("/get_servers", { episode_token: epToken })
    .done(function (data) {
      $("#serverSelection").html(data).show();
      $("html, body").animate({ scrollTop: $("#serverSelection").offset().top - 20 }, 600);
    })
    .fail(function (xhr) {
      console.error("Servers failed:", xhr.status, xhr.responseText);
      $("#serverSelection").html("<p class='text-center text-danger'>Error loading servers.</p>");
    });
}

function selectServer(epToken, serverValue) {
  $("#subtitleSelection").html("<p class='text-center'>Loading subtitles...</p>").show();
  $("#stream").hide();

  $.post("/get_subtitles", {
    episode_token: epToken,
    server: serverValue
  })
    .done(function (data) {
      $("#subtitleSelection").html(data).show();
      $("html, body").animate({ scrollTop: $("#subtitleSelection").offset().top - 20 }, 600);
    })
    .fail(function (xhr) {
      console.error("Subtitles failed:", xhr.status, xhr.responseText);
      $("#subtitleSelection").html("<p class='text-center text-danger'>Error loading subtitles.</p>");
    });
}

function selectSubtitle(epToken, serverValue, subtitleValue) {
  $("#stream").html("<p class='text-center'>Loading stream...</p>").show();

  $.post("/stream", {
    episode_token: epToken,
    server: serverValue,
    subtitle: subtitleValue
  })
    .done(function (data) {
      $("#stream").html(data).show();
      $("html, body").animate({ scrollTop: $("#stream").offset().top - 20 }, 600);
    })
    .fail(function (xhr) {
      console.error("Stream failed:", xhr.status, xhr.responseText);
      $("#stream").html("<p class='text-center text-danger'>Error loading stream.</p>");
    });
}

function processAllEpisodes(animeId) {
  $("#stream").html("<p class='text-center'>Processing all episodes...</p>").show();
  $("#results, #episodes, #serverSelection, #subtitleSelection").hide();

  $.post("/process_all", { anime_id: animeId })
    .done(function (data) {
      $("#stream").html(data).show();
      $("html, body").animate({ scrollTop: $("#stream").offset().top - 20 }, 600);
    })
    .fail(function (xhr) {
      console.error("Process all failed:", xhr.status, xhr.responseText);
      $("#stream").html("<p class='text-center text-danger'>Error processing episodes.</p>");
    });
}
