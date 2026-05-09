let allVideos = [];
let metrics = {};

async function loadData() {
  const [videosResponse, metricsResponse] = await Promise.all([
    fetch("videos.json"),
    fetch("metrics.json")
  ]);

  allVideos = await videosResponse.json();
  metrics = await metricsResponse.json();

  renderMetrics();
  populateFilters();
  renderTopicChart();
  renderTable(allVideos);
}

function renderMetrics() {
  const latestRun = metrics.latest_run || {};
  const lastUpdated = latestRun.finished_at || "Unknown";

  const cards = [
    ["Tracked Channels", metrics.tracked_channels || 0],
    ["Indexed Videos", metrics.total_videos || 0],
    ["Transcript Coverage", `${metrics.transcript_coverage_percent || 0}%`],
    ["Last Updated", formatDate(lastUpdated)]
  ];

  const container = document.getElementById("metricsCards");
  container.innerHTML = cards.map(([label, value]) => `
    <div class="card">
      <div class="label">${escapeHtml(label)}</div>
      <div class="value">${escapeHtml(String(value))}</div>
    </div>
  `).join("");
}

function populateFilters() {
  const channelFilter = document.getElementById("channelFilter");
  const topicFilter = document.getElementById("topicFilter");

  const channels = [...new Set(allVideos.map(v => v.channel_name).filter(Boolean))].sort();
  const topics = [...new Set(allVideos.flatMap(v => v.topics || []))].sort();

  channels.forEach(channel => {
    const option = document.createElement("option");
    option.value = channel;
    option.textContent = channel;
    channelFilter.appendChild(option);
  });

  topics.forEach(topic => {
    const option = document.createElement("option");
    option.value = topic;
    option.textContent = topic;
    topicFilter.appendChild(option);
  });

  document.getElementById("searchInput").addEventListener("input", applyFilters);
  channelFilter.addEventListener("change", applyFilters);
  topicFilter.addEventListener("change", applyFilters);
  document.getElementById("transcriptFilter").addEventListener("change", applyFilters);
}

function applyFilters() {
  const search = document.getElementById("searchInput").value.toLowerCase();
  const channel = document.getElementById("channelFilter").value;
  const topic = document.getElementById("topicFilter").value;
  const transcriptStatus = document.getElementById("transcriptFilter").value;

  const filtered = allVideos.filter(video => {
    const text = [
      video.title,
      video.summary,
      video.channel_name,
      ...(video.key_claims || []),
      ...(video.topics || []),
      ...(video.models_mentioned || []),
      video.relation_to_other_channels
    ].join(" ").toLowerCase();

    const matchesSearch = !search || text.includes(search);
    const matchesChannel = !channel || video.channel_name === channel;
    const matchesTopic = !topic || (video.topics || []).includes(topic);
    const matchesTranscript = !transcriptStatus || video.transcript_status === transcriptStatus;

    return matchesSearch && matchesChannel && matchesTopic && matchesTranscript;
  });

  renderTable(filtered);
}

function renderTopicChart() {
  const container = document.getElementById("topicChart");
  const topTopics = metrics.top_topics || [];

  if (!topTopics.length) {
    container.innerHTML = "<p>No topic data yet.</p>";
    return;
  }

  const max = Math.max(...topTopics.map(item => item[1]));

  container.innerHTML = topTopics.map(([topic, count]) => {
    const width = max ? Math.round((count / max) * 100) : 0;

    return `
      <div class="chart-row">
        <div class="chart-label">${escapeHtml(topic)}</div>
        <div class="bar-bg">
          <div class="bar" style="width: ${width}%"></div>
        </div>
        <div>${count}</div>
      </div>
    `;
  }).join("");
}

function renderTable(videos) {
  const tbody = document.getElementById("videoTable");

  if (!videos.length) {
    tbody.innerHTML = `
      <tr>
        <td colspan="10">No videos match the current filters.</td>
      </tr>
    `;
    return;
  }

  tbody.innerHTML = videos.map(video => `
    <tr>
      <td>${escapeHtml(formatDate(video.published_at))}</td>
      <td>${escapeHtml(video.channel_name || "")}</td>
      <td><strong>${escapeHtml(video.title || "")}</strong></td>
      <td>${renderBadges(video.topics || [])}</td>
      <td>${escapeHtml(video.summary || "No transcript-based summary available.")}</td>
      <td>${renderClaims(video.key_claims || [])}</td>
      <td>${renderBadges(video.models_mentioned || [])}</td>
      <td>${escapeHtml(video.relation_to_other_channels || "")}</td>
      <td>${video.confidence !== null && video.confidence !== undefined ? escapeHtml(String(video.confidence)) : ""}</td>
      <td><a href="${video.url}" target="_blank" rel="noopener noreferrer">Watch</a></td>
    </tr>
  `).join("");
}

function renderBadges(items) {
  if (!items.length) return "";
  return items.map(item => `<span class="badge">${escapeHtml(item)}</span>`).join("");
}

function renderClaims(claims) {
  if (!claims.length) return "";
  return `
    <ul class="claims">
      ${claims.slice(0, 3).map(claim => `<li>${escapeHtml(claim)}</li>`).join("")}
    </ul>
  `;
}

function formatDate(value) {
  if (!value) return "Unknown";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value.slice(0, 10);
  }

  return date.toISOString().slice(0, 10);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

loadData().catch(error => {
  console.error(error);
  document.body.innerHTML = `
    <main>
      <section class="panel">
        <h1>Data loading error</h1>
        <p>Please make sure videos.json and metrics.json were generated.</p>
      </section>
    </main>
  `;
});