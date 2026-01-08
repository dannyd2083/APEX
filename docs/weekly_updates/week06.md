# 🗓 Weekly Project Update

**Project Title:** AI Battle Bots with MCP

**Week #:** 6

**Date:** October 23, 2025 

**Team Members:**  Alyssa Rusk, Nina Qiu, Wania Imran

**Mentor / Instructor:**  Alex Dow & Ermis Catevatis

---
## 1. Summary

This week the team created the orchestrator agent which will be the "brain" of the project. The focus was on connecting it to AnythingLLM and the bridge to Kail MCP. Different database options were researched to use as a way of keeping track of attacks and their results. 

*Slides for this week can be found [here](https://docs.google.com/presentation/d/11qFe_EWwVb2tTE60Ytk2qJ8xDXkFMuBduxbS4duqUnM/edit?usp=sharing).*

---
## 2. Progress
| Task | Assigned To | Status | Notes |
|------|-------------|--------|-------|
| Document new configuration for project | Nina | Completed | README was updated and team members were able to recreate. |
| Create orchestrator agent and connect to AnythingLLM | Alyssa | Completed | Agent is able to connect and query an AnythingLLM workspace. |
| Connect bridge MCP to orchestrator agent | Nina| In Progress | Working on connecting the MCP to the agent instead of AnythingLLM.|
| Research different database options | Wania | Completed | Group decision was reached.|

---
## 3. Key Learnings / Issues
- Everyone got set up with the new configuration!
- Database decision
    - First choice is to use Obsidian so that this RAG implementation will match that of Redstack DB
    - Will confirm after Ermis walkthrough 
    - If this does not seem right, will go with Postgres
- Orchestrator can connect directly to a specified workspace in AnythingLLM
    - That means all the configurations can be set up in the desktop app 
    - User would be able to use whatever model they have set there

---
## 4. Next Steps
| Action Item | Owner | Due Date |
|--------------|-------|----------|
| Add to orchestrator agent logic to begin attack chains (using Redstack) | Alyssa | Oct. 30 |
| Implement Obsidian RAG for orchestrator agent | Wania | Oct. 30 |
| Modify MCP to ensure agents are able to use the tools properly | Nina | Oct. 30 |
| Start summarizer agent | Nina | Oct. 30 |

---
## 5. Blockers / Help Needed
- Ermis will demo the Redstack DB setup

---
## 6. Next Meeting
**Date / Time:** October 30, 2025, 10-11am 

**Agenda:**  
- Demo orchestrator agent 
    - What can it do 
    - What does it still need to do 
- Discuss implementation of summarizer agent