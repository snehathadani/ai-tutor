# 90-second demo walkthrough

## 0:00 — 0:10: Open the app
Show the dark landing page. Explain: "This is a probability tutor for a 12-year-old. It uses your voice, not typing."

## 0:10 — 0:25: Connect
Type a room name and identity, click Connect. Show the token call in the network tab (`/api/token`) and the LiveKit room connecting. The tutor greets the student: "Hi! I am your probability tutor. What would you like to work on?"

## 0:25 — 0:45: A Socratic turn
Student asks: "What is probability?" or tries a problem. The tutor answers with a short hint or a leading question, not a long lecture. Show the live transcript panel updating.

## 0:45 — 1:05: Problem + mastery ring
Tutor calls `get_problem` (probability as a fraction). The student answers. Tutor calls `grade_answer`, and the mastery panel updates: the ring for "Probability as a fraction" fills from level 0 to 1.

## 1:05 — 1:20: Disconnect and summary
Click Disconnect. The session ends, the agent writes a summary to Redis, and the frontend polls `/api/sessions/{sid}/summary` and displays strengths and next steps.

## 1:20 — 1:30: Architecture note
Flip to the README diagram. Say: "Agent is the only Redis writer, API is read-only, Redis is the single state store."
