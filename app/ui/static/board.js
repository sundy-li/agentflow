function renderTask(task) {
  return `
    <article class="task">
      <div><a href="${task.url}" target="_blank">#${task.number} ${task.title}</a></div>
      <small>Type: ${task.type}${task.assignee ? ` | @${task.assignee}` : ""}</small>
      <small>${task.is_stale ? "stale" : "active"}</small>
    </article>
  `;
}

async function refreshBoard() {
  const response = await fetch("/api/board");
  const data = await response.json();
  Object.entries(data.columns).forEach(([state, tasks]) => {
    const column = document.querySelector(`.column[data-state="${state}"] .tasks`);
    if (!column) {
      return;
    }
    column.innerHTML = tasks.map(renderTask).join("");
  });
  const updatedAt = document.getElementById("updatedAt");
  if (updatedAt) {
    updatedAt.textContent = data.updated_at;
  }
}

refreshBoard();
setInterval(refreshBoard, (window.AGENTFLOW_REFRESH_SECONDS || 5) * 1000);

