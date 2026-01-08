# 🗓 Weekly Project Update

**Project Title:** AI Battle Bots with MCP

**Week #:** 10

**Date:** November 20, 2025 

**Team Members:**  Alyssa Rusk, Nina Qiu, Wania Imran

**Mentor / Instructor:**  Alex Dow & Ermis Catevatis

---
## 1. Summary

This week the team got worked on tweaking the prompts to return better results and work with multiple attack chains. Additionally, logging to the database was finalized to ensure all logging is consistent between runs. Finally, a start up script was created and code was cleaned up to ensure a more clean project to pass over to anyone new joining the project. 

*Slides for this week can be found [here](https://docs.google.com/presentation/d/1p6SO4QMLrtkGkIAG9QN6XllYQ-s0L6KM9aD06khc2fw/edit?usp=sharing).*

---
## 2. Progress
| Task | Assigned To | Status | Notes |
|------|-------------|--------|-------|
| Create start up script | Nina | Completed | Created script to start up all needed VMs & MCPs. |
| Start multi-threading for agent | Nina | In progress | Researched and found not possible. Dividing tasks between agents instead. |
| Refactored prompt code | Alyssa | Completed | Cleaned code and made easier for collaboration & version comparison. |
| Refined prompts | Alyssa | Completed | Modified attack chain and execution prompts to try multiple chains. |
| Standardized all logging to Postres DB | Wania | Completed | Logging is consistent across all runs now. | 
| Removed redundant entries from database and added logging to execution phase | Wania | Completed | Cleaned entries and ensured execution-phase events are logged |

---
## 3. Key Learnings / Issues
- Cleaned up project 
    - Helping for future use of project
- Researched multi-threading with LLM queries 
    - Not possible but can possibly divide query between agents 
- Prompts were updated to try out multiple attack chains and write better output
- Execution phase takes extremely long 
- Results from queries are not always consistent

---
## 4. Next Steps
| Action Item | Owner | Due Date |
|--------------|-------|----------|
| More testing & verify gaining shell with LLMs | Alyssa | Nov. 27 |
| Continue with multi-agent setup | Nina | Nov. 27 |
| Add multi-agent setup for other steps | Wania | Nov. 27 |
| Explore options for further usability | Everyone | Nov. 27 |

---
## 5. Blockers / Help Needed
- N/A

---
## 6. Next Meeting
**Date / Time:** November 27, 2025, 10-11am 

**Agenda:**  
- Updates on results & time improvements 
