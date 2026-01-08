# 🗓 Weekly Project Update

**Project Title:** AI Battle Bots with MCP

**Week #:** 8

**Date:** November 6, 2025 

**Team Members:**  Alyssa Rusk, Nina Qiu, Wania Imran

**Mentor / Instructor:**  Alex Dow & Ermis Catevatis

---
## 1. Summary

This week the team worked on building out the logic of the orchestrator agent. 
Currently, the agent can scan and identify vulnerabilities of the target and then pass this information to the next query.
The next query uses this information to prompt the LLM + Redstack MCP for an attack chain. 

*Slides for this week can be found [here](https://docs.google.com/presentation/d/1lAHpBhhFOBkwOd_ES-alHYZB4YC1USzPkvniMRtgotE/edit?usp=sharing).*

---
## 2. Progress
| Task | Assigned To | Status | Notes |
|------|-------------|--------|-------|
| Research DVL attacks | Everyone | Completed | Little resources. Switched to Metasploitable 2. |
| Set up recon portion of orchestrator | Alyssa| Completed | Orchestrator scans target to identify vulnerabilities and makes recommendations. Prompt needs refinement. |
| Set up attack chain portion of orchestrator | Nina | Completed | Connected to Redstack MCP. Prompt needs refinement. |
| Set up Postres DB | Wania | In progress | Completed table schema and set up with orchestrator.py, need to work on connection between DB and project | 

---
## 3. Key Learnings / Issues
- Tried to research attacks on DVL 
    - Very little resources found 
    - Switched to Metaploitable 2 for the initial target as:
        - Set up is easier 
        - More resources 
- Set up orchestrator to use both Open Router and AnythingLLM
    - Different queries worked better for different portions 
    - Uses output from one query to feed into the next

---
## 4. Next Steps
| Action Item | Owner | Due Date |
|--------------|-------|----------|
| Set orchestrator to execute attack chain | Alyssa | Nov. 13 |
| Fine-tune prompting | Nina | Nov. 13 |
| Fix any DB integration | Wania | Nov. 13 |


---
## 5. Blockers / Help Needed
- Should the process be cyclic?
    - How to tell when the agent should be "done?"
    - To discuss in meeting

---
## 6. Next Meeting
**Date / Time:** November 13, 2025, 10-11am 

**Agenda:**  
- Show off full orchestrator and its logic
- Show DB and its logs 
    - Hopefully see improvements in logs as model is fine-tuned
