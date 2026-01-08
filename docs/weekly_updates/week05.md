# 🗓 Weekly Project Update

**Project Title:** AI Battle Bots with MCP

**Week #:** 5

**Date:** October 16, 2025 

**Team Members:**  Alyssa Rusk, Nina Qiu, Wania Imran

**Mentor / Instructor:**  Alex Dow & Ermis Catevatis

---
## 1. Summary

This week the team worked on sorting out running open-source models through the lab computers (last week decided our personal devices were not strong enough) while connecting it with Kali MCP. We were also trouble-shooting issues with the current Kali MCP setup. Because of permission issues in the lab, we had to adjust and use a bridge MCP and connecting to a Kali VM. This also resolved the Kali MCP issues and will be the setup we use going forward. Slides for this week can be found [here](https://docs.google.com/presentation/d/14cAKFHXJLqkzhpDvDlyOBCWavQREM8BNjlPkHBcOq-0/edit?slide=id.g4dfce81f19_0_45#slide=id.g4dfce81f19_0_45).

---
## 2. Progress
| Task | Assigned To | Status | Notes |
|------|-------------|--------|-------|
| Get open-source setup running on lab computers | Nina | Completed | Can run Kali commands to scan DVL. Had to set up bridge MCP to be run with Kali VM. |
| Troubleshoot Kali MCP interactions with LLM | Alyssa & Wania | Closed | Hallucinates or refuses to scan DVL - going with bridge MCP with Kali VM solution.|
| Research AnythingLLM timeout | Alyssa & Nina| In Progress | Seems like you can turn this off in config. May need to run as Docker container though.|
| Begin research on implementing RAG | Alyssa | In Progress | Needing to update RAG with command output could pose an issue. Need to discuss with mentors.|

---
## 3. Key Learnings / Issues
- A bridge MCP connecting to a Kali VM works better than Kali MCP
    - Using closed-source with Kali MCP resulted in various issues
- Timeouts are still a problem for long commands
    - If there is a timeout the model thinks it "can't connect"
    - Seems like there is a way to [remove the timeout](https://www.reddit.com/r/LocalLLaMA/comments/1dhxaoo/larger_models_stop_responding/)

---
## 4. Next Steps
| Action Item | Owner | Due Date |
|--------------|-------|----------|
| Fix model timeout issues| Nina | Oct. 23 |
| Implement RAG with Kali outputs | Alyssa | Oct. 23 |
| Start creating Redstack MCP | Wania | Oct. 23 |

---
## 5. Blockers / Help Needed
- Questions about continuous RAG updates (to be asked in meeting)
- Need access to Redstack DB

---
## 6. Next Meeting
**Date / Time:** October 23, 2025, 10-11am 

**Agenda:**  
- Discuss timeout solution 
- Go over RAG implementation
- Explain Redstack MCP setup