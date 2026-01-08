# 🗓 Weekly Project Update

**Project Title:** AI Battle Bots with MCP

**Week #:** 9

**Date:** November 13, 2025 

**Team Members:**  Alyssa Rusk, Nina Qiu, Wania Imran

**Mentor / Instructor:**  Alex Dow & Ermis Catevatis

---
## 1. Summary

This week the team got logging set up between the orchestrator and the database. The execution section of the orchestrator was also initialized. Finally, refactoring was done to ensure clean code and reduce merge conflicts. 

*Slides for this week can be found [here](https://docs.google.com/presentation/d/1NryY6arzBkv9pWHWU0HrTuBrWyQdFpEkd7TCmyKnbCU/edit?usp=sharing).*

---
## 2. Progress
| Task | Assigned To | Status | Notes |
|------|-------------|--------|-------|
| Refactoring | Nina | Completed | Reorganized and fixed all code between orchestrator and logger. |
| Set up fresh scan option to reuse past scans | Alyssa| In progress | Needs testing |
| Set up initial execution section of orchestrator | Alyssa | Completed | Executes commands. Prompt needs refinement and testing. |
| Finish set up of Postres DB | Wania | Completed | Completed table schema between DB and project | 

---
## 3. Key Learnings / Issues
- Refactoring needed to make collaboration easier 
- Need to standardize logging so that database entries
- Orchestrator can run commands from execution section and return results but needs fine-tuning 
    - May look at writing to a local json in addition to DB logging just to make testing/fine-tuning easier

---
## 4. Next Steps
| Action Item | Owner | Due Date |
|--------------|-------|----------|
| Fine-tune model | Alyssa | Nov. 20 |
| Fine-tune prompting | Nina | Nov. 20 |
| Standardize logging to database | Wania | Nov. 20 |
| Research attack chains for Metasploit 2 | Everyone | Nov. 20 |


---
## 5. Blockers / Help Needed
- N/A

---
## 6. Next Meeting
**Date / Time:** November 20, 2025, 10-11am 

**Agenda:**  
- Show off changes and improvements to orchestrator 
- Have clean logs properly formatting in database
