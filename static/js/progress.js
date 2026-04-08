const API_BASE = "";

async function loadProgress() {
    try {
        const res = await fetch(`${API_BASE}/get-user-sessions`);
        if (!res.ok) throw new Error("Failed to fetch sessions");
        
        const sessions = await res.json();
        
        if (sessions.length === 0) {
            document.querySelector(".container").innerHTML += "<p style='text-align:center;'>No interview sessions found. Start an interview to see your progress!</p>";
            return;
        }

        // OVERVIEW
        document.getElementById("totalSessions").innerText = sessions.length;

        // Process scores as numbers, handling potential string/decimal formats
        const numericScores = sessions.map(s => parseFloat(s.score) || 0);
        const totalScore = numericScores.reduce((sum, score) => sum + score, 0);
        const avgScore = totalScore / sessions.length;
        
        document.getElementById("avgScore").innerText = isNaN(avgScore) ? "0.0" : avgScore.toFixed(1);
        document.getElementById("latestScore").innerText = numericScores[0].toFixed(1);

        // SKILL PROGRESS & PERCENTAGES
        const normalizedAvg = isNaN(avgScore) ? 0 : avgScore;
        const techVal = normalizedAvg;
        const commVal = normalizedAvg * 0.95;
        const confVal = normalizedAvg * 0.9;

        document.getElementById("techSkill").value = techVal;
        document.getElementById("commSkill").value = commVal;
        document.getElementById("confSkill").value = confVal;

        document.getElementById("techPct").innerText = Math.round(techVal * 10) + "%";
        document.getElementById("commPct").innerText = Math.round(commVal * 10) + "%";
        document.getElementById("confPct").innerText = Math.round(confVal * 10) + "%";

        document.getElementById("bestSkill").innerText = sessions.length > 0 ? (sessions[0].topic.split('|')[0] || "General") : "-";

        // SKILLS TO DEVELOP
        const skillsContainer = document.getElementById("skillsToDevelop");
        if (sessions.length > 0 && sessions[0].feedback) {
            const feedback = sessions[0].feedback;
            const improvementMatch = feedback.match(/## Critical Areas for Improvement[:\s]*([\s\S]*?)(?=\n##|$)/i);
            
            if (improvementMatch) {
                const points = improvementMatch[1].trim().split('\n').filter(p => p.trim().startsWith('-'));
                if (points.length > 0) {
                    skillsContainer.innerHTML = points.map(p => {
                        const skill = p.replace('-', '').trim();
                        return `<div class="skill-tag"><i class="ph-bold ph-trend-up"></i> ${skill}</div>`;
                    }).join('');
                }
            }
        }

        // SESSION TABLE
        const table = document.getElementById("sessionTable");
        table.innerHTML = ""; // Clear existing
        
        sessions.forEach(s => {
            const row = document.createElement("tr");
            const date = new Date(s.session_date).toLocaleDateString();
            
            const feedbackText = s.feedback || "Review Pending";
            const topicText = s.topic || "General Interview";
            const scoreText = (parseFloat(s.score) || 0).toFixed(1);

            // Truncate feedback if too long
            const displayFeedback = feedbackText.length > 100 
                ? feedbackText.substring(0, 100) + "..." 
                : feedbackText;
                
            row.innerHTML = `
                <td>${date}</td>
                <td title="${topicText}">${topicText}</td>
                <td><strong>${scoreText}/10</strong></td>
                <td><small>${displayFeedback}</small></td>
                <td><a href="/feedback/${s.session_id}" class="btn-secondary" style="padding: 5px 10px; font-size: 0.8rem;">View</a></td>
            `;
            table.appendChild(row);
        });

    } catch (e) {
        console.error("Load progress error:", e);
        // alert("Failed to load progress data.");
    }
}

// Initialize on load
document.addEventListener("DOMContentLoaded", loadProgress);
