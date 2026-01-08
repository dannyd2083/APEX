# 🗓 Weekly Project Update

**Project Title:** AI Battle Bots with MCP

**Week #:** 11

**Date:** November 27, 2025 

**Team Members:**  Alyssa Rusk, Nina Qiu, Wania Imran

**Mentor / Instructor:**  Alex Dow & Ermis Catevatis

---
## 1. Summary

This week the team explored the accuracy of the command generation the LLM was producing and also researched solutions to Metasploit session commands. 
The team also worked on multi-threading...

*Slides for this week can be found [here](https://docs.google.com/presentation/d/1gV_v1NikUFdbQBhVn1hpbJMVWyXWM4n_HqZEVUIZBLk/edit?usp=sharing).*

---
## 2. Progress
| Task | Assigned To | Status | Notes |
|------|-------------|--------|-------|
| Set up multi-threading | Nina | Complete | Need to do final testing for verification |
| Fixed output files | Alyssa | Completed | Made all local output files clean consistent JSON files |
| Research Metasploit commands | Alyssa | Completed | Commands mostly work but need session command integration |
|  | Wania |  |  | 


---
## 3. Key Learnings / Issues
- Attack chain generation is mostly suggesting applicable Metasploit modules
- Need to be able to run Metasploit session commands
- Issues when executing commands
    - Agent was sending in it's thought process instead of actual command
    - Need timeout exit for execution calls that are not responsive
- Try to figure out why the same command was ran multiple times with the same flags

---
## 4. Next Steps
| Action Item | Owner | Due Date |
|--------------|-------|----------|
| Fix execution issues | Nina | Dec. 4 |
| Integrate Metasploit session commands | Alyssa | Dec. 4 |
| Add Mitre mapping to DB | Wania | Dec. 4 |

---
## 5. Blockers / Help Needed
- Out of Open Router tokens
    - Each execution takes around \$1, need to balance between faster execution time vs cost

---
## 6. Next Meeting
**Date / Time:** December 4, 2025, 10-11am 

**Agenda:**  
- Updates on multi-threading and Metasploit sessions
