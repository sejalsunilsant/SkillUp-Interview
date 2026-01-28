// SAMPLE DATA (replace with API later)
const sessions = [
  {
    date: "2026-01-20",
    topic: "Git",
    score: 7,
    feedback: "Clear explanation, needs examples",
    skills: { tech: 7, comm: 6, conf: 6 }
  },
  {
    date: "2026-01-24",
    topic: "DBMS",
    score: 8,
    feedback: "Well structured answer",
    skills: { tech: 8, comm: 7, conf: 7 }
  },
  {
    date: "2026-01-27",
    topic: "System Design",
    score: 9,
    feedback: "Excellent clarity and confidence",
    skills: { tech: 9, comm: 8, conf: 8 }
  }
];

// OVERVIEW
document.getElementById("totalSessions").innerText = sessions.length;

const avgScore =
  sessions.reduce((sum, s) => sum + s.score, 0) / sessions.length;
document.getElementById("avgScore").innerText = avgScore.toFixed(1);

document.getElementById("latestScore").innerText =
  sessions[sessions.length - 1].score;

// SKILL AVERAGES
const avg = key =>
  sessions.reduce((sum, s) => sum + s.skills[key], 0) / sessions.length;

document.getElementById("techSkill").value = avg("tech");
document.getElementById("commSkill").value = avg("comm");
document.getElementById("confSkill").value = avg("conf");

// BEST SKILL
const skillMap = {
  Technical: avg("tech"),
  Communication: avg("comm"),
  Confidence: avg("conf")
};

document.getElementById("bestSkill").innerText =
  Object.keys(skillMap).reduce((a, b) =>
    skillMap[a] > skillMap[b] ? a : b
  );

// SESSION TABLE
const table = document.getElementById("sessionTable");
sessions.forEach(s => {
  const row = document.createElement("tr");
  row.innerHTML = `
    <td>${s.date}</td>
    <td>${s.topic}</td>
    <td>${s.score}/10</td>
    <td>${s.feedback}</td>
  `;
  table.appendChild(row);
});
