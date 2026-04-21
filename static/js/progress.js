const API_BASE = "";

async function loadProgress() {
    try {
        // Fetch profile info (Streak, Status)
        const profileRes = await fetch(`${API_BASE}/user-profile`);
        if (profileRes.ok) {
            const profile = await profileRes.json();
            const info = profile.streak_info;
            
            // Update Streak UI
            const streakCount = info.streak_count || 0;
            document.getElementById("streakCount").innerText = `${streakCount} Day${streakCount !== 1 ? 's' : ''}`;
            
            const streakPct = Math.min((streakCount / 7) * 100, 100);
            document.getElementById("streakProgress").style.width = `${streakPct}%`;
            document.getElementById("streakGoal").innerText = `${streakCount % 7}/7 days to next milestone`;
            
            // Update Today's Status UI
            const status = info.today_status;
            document.getElementById("todayStatus").innerText = status;
            
            const nextAvail = document.getElementById("nextAvailable");
            if (status === 'Completed') {
                document.getElementById("todayStatus").style.color = "#48cfad";
                nextAvail.innerText = `Next session in ${info.hours_until_next} hours`;
            } else {
                nextAvail.innerText = "Take your interview now!";
            }

            // Streak Badges Milestone
            const skillsContainer = document.getElementById("skillsToDevelop");
            if (streakCount >= 7) {
                const badge = `<div class="skill-tag" style="background: linear-gradient(135deg, #fbc531, #e1b12c);"><i class="ph-bold ph-medal"></i> 7-Day Warrior Badge</div>`;
                skillsContainer.innerHTML = badge + skillsContainer.innerHTML;
            }
            if (streakCount >= 30) {
                const badge = `<div class="skill-tag" style="background: linear-gradient(135deg, #9c88ff, #483d8b);"><i class="ph-bold ph-trophy"></i> 30-Day Master Badge</div>`;
                skillsContainer.innerHTML = badge + skillsContainer.innerHTML;
            }
        }

        const res = await fetch(`${API_BASE}/get-user-sessions`);
        if (!res.ok) throw new Error("Failed to fetch sessions");
        
        const sessions = await res.json();
        
        if (sessions.length === 0) {
            const container = document.querySelector(".container");
            if (!container.querySelector(".empty-msg")) {
                container.innerHTML += "<p class='empty-msg' style='text-align:center; padding: 20px;'>No interview sessions found. Start an interview to see your progress!</p>";
            }
            return;
        }

        // OVERVIEW
        document.getElementById("totalSessions").innerText = sessions.length;

        // Process scores as numbers, handling potential string/decimal formats
        const numericScores = sessions.filter(s => s.score !== null).map(s => parseFloat(s.score) || 0);
        const totalScore = numericScores.reduce((sum, score) => sum + score, 0);
        const avgScore = numericScores.length > 0 ? (totalScore / numericScores.length) : 0;
        
        document.getElementById("avgScore").innerText = isNaN(avgScore) ? "0.0" : avgScore.toFixed(1);
        // document.getElementById("latestScore").innerText = numericScores.length > 0 ? numericScores[0].toFixed(1) : "-"; // Element removed in UI update

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

        // document.getElementById("bestSkill").innerText = sessions.length > 0 ? (sessions[0].topic.split('|')[0] || "General") : "-"; // Element removed

        // SKILLS TO DEVELOP
        const skillsContainer = document.getElementById("skillsToDevelop");
        if (sessions.length > 0 && sessions[0].feedback) {
            const feedback = sessions[0].feedback;
            const improvementMatch = feedback.match(/## Critical Areas for Improvement[:\s]*([\s\S]*?)(?=\n##|$)/i);
            
            if (improvementMatch) {
                const points = improvementMatch[1].trim().split('\n').filter(p => p.trim().includes('-'));
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
            const scoreText = s.score !== null ? (parseFloat(s.score) || 0).toFixed(1) : "Pnd";

            // Truncate feedback if too long
            const displayFeedback = feedbackText.length > 100 
                ? feedbackText.substring(0, 100) + "..." 
                : feedbackText;
                
            row.innerHTML = `
                <td>${date}</td>
                <td title="${topicText}">${topicText}</td>
                <td><strong>${scoreText !== "Pnd" ? scoreText + "/10" : "Pending"}</strong></td>
                <td><small>${displayFeedback}</small></td>
                <td><a href="/feedback/${s.session_id}" class="btn-secondary" style="padding: 5px 10px; font-size: 0.8rem;">View</a></td>
            `;
            table.appendChild(row);
        });

    } catch (e) {
        console.error("Load progress error:", e);
    }
}

// Initialize on load
document.addEventListener("DOMContentLoaded", loadProgress);
