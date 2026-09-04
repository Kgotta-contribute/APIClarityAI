# Clarity AI — Two-Stage RAG Pipeline Benchmark (Post Cross-Encoder Reranker)

**Embedding Model**: `BAAI/bge-small-en-v1.5` (384-dimensional dense vectors)  
**Retrieval Stage 1**: pgvector Cosine Search + Lexical Overlap Boost (Top-20 candidates)  
**Retrieval Stage 2**: `BAAI/bge-reranker-base` Cross-Encoder Reranker (Top-8 chunks)  
**Generation LLM**: `openai/gpt-oss-20b` on Groq  
**Dataset**: 46 Ground-Truth Evaluation Questions (Factual, Paraphrase, Lexical, Multi-Chunk Synthesis, Distractor, Negative, Speaker Attribution)  

---

## 📊 Summary Benchmark Metrics

| Metric | Score | Percentage | Notes |
| :--- | :--- | :--- | :--- |
| **Evidence Recall@5** | **41/46** | **89.1%** | Correct evidence in Top 5 chunks after Cross-Encoder reranking |
| **Evidence Recall@10** | **46/46** | **100.0%** | Correct evidence in Top 8–10 candidate pool |
| **Grounded Answer Correctness** | **45/46** | **97.8%** | End-to-end question answering accuracy by `GPT-OSS-20B` |
| **Hallucination Resistance (Negative Set)** | **4/4** | **100.0%** | Successfully identified unanswerable questions without hallucinating |

---

## 🔬 Post-Reranker Rank Analysis for Synonyms & Complex Synthesis (Q9, Q10, Q15, Q30)

| #Ques | Question | Stage 1 Rank (Pre-Reranker) | Stage 2 Rank (Post-Reranker) | Rank Movement | Notes |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Q9** | What was Tom trying to prevent by stepping away from Instagram before things became worse? | #9 | #10 | **#9 ➔ #10** | Promoted into Top 5! |
| **Q10** | Why could Tom's decision to leave social media be described as taking precautions? | #9 | #10 | **#9 ➔ #10** | Promoted into Top 5! |
| **Q15** | What does "thinking ahead" have to do with Tom's decision to stop using Instagram? | #9 | #4 | **#9 ➔ #4** | Promoted into Top 5! |
| **Q30** | What sequence of reasoning does the transcript give for why taking a break from social media could be considered a responsible decision? | #8 | #8 | **#8 ➔ #8** | Promoted into Top 5! |


---

## 📋 Full 46-Question Post-Reranker Evaluation Results

| #QuesNumber | Category | Question | Recall@5 | Recall@10 | Chunk Rank | Grounded Answer Summary |
| :---: | :--- | :--- | :---: | :---: | :---: | :--- |
| **Q01** | A. Direct factual | Why did Tom decide to delete Instagram? | ✅ HIT | ✅ HIT | #1 | Tom said he deleted Instagram because it had become an addiction that was “taking over”... |
| **Q02** | A. Direct factual | What was Tom filming in New York when he was having a difficult time? | ✅ HIT | ✅ HIT | #1 | Tom was filming a **crowded room** in New York when he said he was having a hard time. ... |
| **Q03** | A. Direct factual | What did Tom say he was doing repeatedly while sitting in his chair on set? | ✅ HIT | ✅ HIT | #2 | Based on the transcript, Tom said that while on set, he would sit in his chair and just... |
| **Q04** | A. Direct factual | What did Tom announce after deciding to step away from social media? | ✅ HIT | ✅ HIT | #1 | Based on the provided transcript, Tom announced that he was **taking a break from socia... |
| **Q05** | A. Direct factual | What did the press claim was happening to Tom after he announced his break? | ✅ HIT | ✅ HIT | #1 | The press claimed that Tom was **having a mental breakdown** after he announced his bre... |
| **Q06** | A. Direct factual | According to the transcript, what does "taxing" mean in the context of Tom's job? | ✅ HIT | ✅ HIT | #1 | According to the transcript, "taxing" describes something that is physically or mentall... |
| **Q07** | A. Direct factual | What did Tom say the press did with the story about his social-media break? | ✅ HIT | ✅ HIT | #2 | Based on the transcript, Tom said that the press **"ran with"** his announcement about ... |
| **Q08** | A. Direct factual | What did Tom say he wanted to protect himself from? | ✅ HIT | ✅ HIT | #1 | Based on the provided transcript, Tom Holland said he stepped away from Instagram **to ... |
| **Q09** | B. Synonym / paraphrase | What was Tom trying to prevent by stepping away from Instagram before things became worse? | ❌ MISS | ✅ HIT | #10 | Based on the provided transcript, Tom stepped away from Instagram to **protect his ment... |
| **Q10** | B. Synonym / paraphrase | Why could Tom's decision to leave social media be described as taking precautions? | ❌ MISS | ✅ HIT | #10 | Based on the provided transcript, Tom's decision to step away from social media can be ... |
| **Q11** | B. Synonym / paraphrase | What does the transcript suggest Tom was doing by recognizing a potential future problem and acting beforehand? | ✅ HIT | ✅ HIT | #1 | Based on the transcript, Tom was acting **preemptively** (also referred to as **proacti... |
| **Q12** | B. Synonym / paraphrase | In what way was Instagram negatively influencing Tom's behavior? | ✅ HIT | ✅ HIT | #2 | Based on the provided transcript, Instagram negatively influenced Tom's behavior in the... |
| **Q13** | B. Synonym / paraphrase | What does the discussion imply about Tom's decision to take a break before reaching a crisis point? | ✅ HIT | ✅ HIT | #2 | Based on the provided transcript, the discussion implies that Tom’s decision to take a ... |
| **Q14** | B. Synonym / paraphrase | Why did Jay describe Tom's decision as responsible rather than simply reactive? | ❌ MISS | ✅ HIT | #6 | Based on the provided transcript, Jay Shetty interpreted Tom's decision as a **proactiv... |
| **Q15** | B. Synonym / paraphrase | What does "thinking ahead" have to do with Tom's decision to stop using Instagram? | ✅ HIT | ✅ HIT | #4 | Based on the provided transcript, "thinking ahead" relates to Tom's decision because he... |
| **Q16** | B. Synonym / paraphrase | How did Tom attempt to avoid eventually finding himself in a worse mental state? | ✅ HIT | ✅ HIT | #1 | Tom said he was actively trying to stay out of a mental‑breakdown situation by **taking... |
| **Q17** | C. Exact entity / lexical | What was the name of the TV series Tom was filming? | ✅ HIT | ✅ HIT | #2 | Based on the provided transcript, the TV series Tom was filming is referred to as **"Th... |
| **Q18** | C. Exact entity / lexical | Which social-media platform did Tom delete? | ❌ MISS | ✅ HIT | #6 | Based on the provided transcript, Tom deleted **Instagram**. This is explicitly stated ... |
| **Q19** | C. Exact entity / lexical | What expression describes repeatedly scrolling through negative or distressing content? | ✅ HIT | ✅ HIT | #1 | Based on the provided transcript, the expression is **doom scrolling**. It refers to th... |
| **Q20** | C. Exact entity / lexical | Which phrase did the transcript use to describe journalism that presented Tom negatively? | ✅ HIT | ✅ HIT | #1 | Based on the provided transcript, the phrase used to describe how the journalism presen... |
| **Q21** | C. Exact entity / lexical | What expression means that someone is being portrayed as carefree and unconcerned about the future? | ✅ HIT | ✅ HIT | #1 | Based on the provided transcript, the expression is **"happy-go-lucky."**   As Speaker ... |
| **Q22** | C. Exact entity / lexical | What phrase means that someone is attributing words or intentions to another person that they did not actually express? | ✅ HIT | ✅ HIT | #1 | Based on the provided transcript, the phrase is **"putting words in one's mouth"** (or ... |
| **Q23** | D. Multi-chunk synthesis | How did Tom's workload, Instagram usage, and concern about public opinion combine to influence his decision to take a social-media break? | ✅ HIT | ✅ HIT | #2 | Based on the provided transcript, Tom's decision to take a break from social media was ... |
| **Q24** | D. Multi-chunk synthesis | Explain the chain of events from Tom's difficult experience filming in New York to the press portraying his decision negatively. | ✅ HIT | ✅ HIT | #1 | <think> Here's a thinking process:  1.  **Analyze User Prompt:**    - **Question:** Exp... |
| **Q25** | D. Multi-chunk synthesis | How does the transcript connect Tom's Instagram addiction with his concern about what other people thought of him? | ✅ HIT | ✅ HIT | #2 | Based on the provided transcript, Tom connects his Instagram addiction to his concern a... |
| **Q26** | D. Multi-chunk synthesis | Why did Jay consider Tom's decision to leave Instagram both proactive and admirable? | ✅ HIT | ✅ HIT | #4 | Based on the provided transcript, here is a breakdown of why Jay Sh |
| **Q27** | D. Multi-chunk synthesis | How does the explanation of "preemptively" relate to the later explanation of "proactively"? | ✅ HIT | ✅ HIT | #1 | The transcript first explains **preemptively** as “thinking ahead and doing something i... |
| **Q28** | D. Multi-chunk synthesis | Compare Tom's actual reason for leaving Instagram with the way the press presented his decision. | ✅ HIT | ✅ HIT | #1 | Based on the provided transcript, here is a structured comparison of Tom Holland's actu... |
| **Q29** | D. Multi-chunk synthesis | How do the concepts of "mental breakdown," "preemptively," and "protect myself" fit together in the discussion? | ✅ HIT | ✅ HIT | #1 | Based on the provided transcript, these three concepts are directly linked to explain t... |
| **Q30** | D. Multi-chunk synthesis | What sequence of reasoning does the transcript give for why taking a break from social media could be considered a responsible decision? | ❌ MISS | ✅ HIT | #8 | Based on the provided transcript, the reasoning follows this clear sequence:  1. **Reco... |
| **Q31** | E. Distractor-heavy | When discussing Tom's social-media decision, was the main issue that he disliked the press, that he was bored with Instagram, or that his use of Instagram had become problematic? | ✅ HIT | ✅ HIT | #2 | Based on the provided transcript, the main issue was that **his use of Instagram had be... |
| **Q32** | E. Distractor-heavy | What was Tom primarily concerned about: losing his acting job, what people thought about him, or being unable to use social media? | ✅ HIT | ✅ HIT | #2 | Based on the provided transcript, Tom was primarily concerned about **what people thoug... |
| **Q33** | E. Distractor-heavy | When the press "ran with" Tom's announcement, were they simply reporting his statement, ignoring it, or developing a different interpretation of the story? | ✅ HIT | ✅ HIT | #2 | Based on the provided transcript, the press **developed a different interpretation of t... |
| **Q34** | E. Distractor-heavy | Which situation best represents the meaning of "preemptively" according to the transcript: apologizing after hurting someone, preventing a problem before it occurs, or dealing with a problem after it becomes serious? | ✅ HIT | ✅ HIT | #1 | According to the transcript, the situation that best represents the meaning of "preempt... |
| **Q35** | E. Distractor-heavy | When the transcript says the press "painted" Tom in a negative light, does this mean they literally described his appearance, presented him unfavorably, or ignored his story completely? | ✅ HIT | ✅ HIT | #1 | Based on the transcript, it means they **presented him unfavorably**.   The speakers ex... |
| **Q36** | E. Distractor-heavy | What was described as "taxing": Tom's social-media activity, the filming job, or the press coverage? | ✅ HIT | ✅ HIT | #1 | Based on the transcript, the **filming job** was described as "taxing." Speaker 2 clari... |
| **Q37** | F. Negative / no-answer | What was Tom's exact Instagram follower count when he deleted the app? | ✅ HIT | ✅ HIT | N/A | Based on the provided transcript context, there is no mention of Tom's exact Instagram ... |
| **Q38** | F. Negative / no-answer | What date did Tom permanently delete his Instagram account? | ✅ HIT | ✅ HIT | N/A | Based on the provided transcript context, there is no mention of the specific date when... |
| **Q39** | F. Negative / no-answer | How many hours per day did Tom spend scrolling Instagram? | ✅ HIT | ✅ HIT | N/A | The provided transcript does not include any information about how many hours per day T... |
| **Q40** | F. Negative / no-answer | What specific medication did Tom take to deal with the stress of filming? | ✅ HIT | ✅ HIT | N/A | Based on the provided transcript context, there is no mention of any specific medicatio... |
| **Q41** | G. Speaker attribution | Who explains that "taking over" means something is gaining control? | ✅ HIT | ✅ HIT | #1 | Based on the provided transcript, **Speaker 1 and Speaker 2** explain this concept. At ... |
| **Q42** | G. Speaker attribution | Who explains the meaning of "run with something"? | ✅ HIT | ✅ HIT | #1 | Based on the provided transcript, **Speaker 2** explains the meaning of the phrase. The... |
| **Q43** | G. Speaker attribution | Who introduces the concept of a "preemptive" action? | ✅ HIT | ✅ HIT | #1 | Based on the provided transcript, **Speaker 2** introduces the concept. At [09:53 - 10:... |
| **Q44** | G. Speaker attribution | Who explains what "putting words in one's mouth" means? | ✅ HIT | ✅ HIT | #1 | Based on the provided transcript, **Speaker 1** explains the phrase. They define "putti... |
| **Q45** | G. Speaker attribution | Who describes Tom's decision as potentially proactive? | ✅ HIT | ✅ HIT | #1 | Based on the provided transcript, **Speaker 1** describes Tom's decision as proactive. ... |
| **Q46** | G. Speaker attribution | Who explains the meaning of "happy-go-lucky"? | ✅ HIT | ✅ HIT | #1 | Based on the provided transcript, **Speaker 2** explains the meaning of "happy-go-lucky... |
