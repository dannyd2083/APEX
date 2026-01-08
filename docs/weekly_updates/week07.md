# 🗓 Weekly Project Update

**Project Title:** AI Battle Bots with MCP

**Week #:** 7

**Date:** October 30, 2025 

**Team Members:**  Alyssa Rusk, Nina Qiu, Wania Imran

**Mentor / Instructor:**  Alex Dow & Ermis Catevatis

---
## 1. Summary

This week the team worked on fixing issues with Kali MCP connections to the orchestrator and testing limitations. The team also reviewed Redstack DB to proposed tools needed for the agents. Milestones were proposed to ensure completion of project. 

*Slides for this week can be found [here](https://docs.google.com/presentation/d/1ROmxwPKAT0w56sTPjLhWsI68IkK8HiAVBi3O-vKZs3s/edit?usp=sharing).*

---
## 2. Progress
| Task | Assigned To | Status | Notes |
|------|-------------|--------|-------|
| Propose remaining milestones | Everyone | Completed | Team proposed milestones to be reviewed by mentors. |
| Review RedstackDB and propose tools for MCP | Everyone | Completed | Proposed tools to be discussed with mentors. |
| Discuss database schema | Everyone | Completed | Will propose schema to mentors. |
| Connect bridge MCP to orchestrator agent | Nina| Completed | Able to connect MCP through OpenRouter instead of AnythingLLM. |
| Fix Kali MCP output bug when connecting | Alyssa | Completed | Modified Kali MCP logging. |
| Test OpenRouter connection to Kali MCP | Nina | Completed | Works well - can perform Metasploit commands |
| Test AnythingLLM connection to Kali MCP | Alyssa | Completed | Queries differ based on workspace | 
| Orchestrator Enhancement & DB Integration Planning | Wania | Completed + In progress| Modified agent to support continuous attack sessions |
| DVL Target Config | Wania | Completed | Troubleshot DVL's read-only filesystem error, deployed SSH (OpenSSH 3.6.1p2 on port 22) services, validated targets through orchestrator | 

---
## 3. Key Learnings / Issues
- AnythingLLM is affected by previous queries in the workspace 
    - Makes a significant difference in success of query 
    - Has RAG integration
- OpenRouter was not affected by previous queries 
    - Higher success rate 
    - Does not have RAG integrated
- Need to decide between prompt management vs RAG integration
- Found timeout settings in Kali MCP and modified 

---
## 4. Next Steps
| Action Item | Owner | Due Date |
|--------------|-------|----------|
| Integrate Redstack MCP | Alyssa | Nov. 6 |
| Integrate Postgres DB | Wania | Nov. 6 |
| Finalize orchestrator logic | Nina | Nov. 6 |


---
## 5. Blockers / Help Needed
- Redstack MCP setup 
- Will meet with Sina if available for agent advice

---
## 6. Next Meeting
**Date / Time:** November 6, 2025, 10-11am 

**Agenda:**  
- Integrate Redstack MCP
- Integrate PostGres DB
- Finalize orchestrator logic 
    - Begin planning what logic should be separated out to different agents
