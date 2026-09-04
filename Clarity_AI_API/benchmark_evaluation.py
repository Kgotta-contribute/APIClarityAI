import json
import math
import os
import re
import ssl
import sys
import time
from pathlib import Path
from typing import Any
from urllib import request

# Force UTF-8 encoding for Windows console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import numpy as np
from app.config.config import settings
from app.services.embedding_service import get_embedding, get_embeddings_batch
from app.services.reranker_service import rerank_chunks
from app.services.local_store import create_sliding_window_chunks

BENCHMARK_QUESTIONS = [
    # A. Deep Paraphrase / Semantic Retrieval
    {
        "id": "Q1",
        "category": "Semantic Retrieval",
        "question": "Why did one interviewee deliberately maintain the same wake-up routine even on a holiday?",
        "expected": "Because they had an established routine and were already awake at 7:00 even though it was a holiday.",
        "key_points": ["established routine", "already awake", "7:00", "holiday"]
    },
    {
        "id": "Q2",
        "category": "Semantic Retrieval",
        "question": "Why did the person who woke at 7:00 on the weekend consider that time normal despite it being a non-working day?",
        "expected": "They had a stable routine and their alarm/routine caused them to get up at that time.",
        "key_points": ["stable routine", "alarm", "get up at that time"]
    },
    {
        "id": "Q3",
        "category": "Semantic Retrieval",
        "question": "What was the underlying reason one participant could not simply sleep later on the day of the race?",
        "expected": "They needed enough time to have breakfast, digest properly, and prepare for the race starting at 9:00.",
        "key_points": ["breakfast", "digest", "race at 9:00"]
    },
    {
        "id": "Q4",
        "category": "Semantic Retrieval",
        "question": "Why did one person's early wake-up on a weekend happen accidentally rather than intentionally?",
        "expected": "Their work alarm was still set from Monday–Friday and they had forgotten to turn it off.",
        "key_points": ["alarm still set", "Monday-Friday", "forgot to turn off"]
    },
    {
        "id": "Q5",
        "category": "Semantic Retrieval",
        "question": "What does the transcript suggest is the practical relationship between someone's commute and their required wake-up time?",
        "expected": "A longer preparation and commute time requires waking earlier; one person needed an hour to prepare, left at 7:20, spent 40 minutes on the metro, and arrived at work at 8:00.",
        "key_points": ["prepare", "leave at 7:20", "40 minutes metro", "arrive at 8:00"]
    },
    {
        "id": "Q6",
        "category": "Semantic Retrieval",
        "question": "Why does one interviewee prefer eating the same breakfast every day?",
        "expected": "To avoid wasting time deciding what to eat.",
        "key_points": ["avoid wasting time", "deciding what to eat"]
    },
    {
        "id": "Q7",
        "category": "Semantic Retrieval",
        "question": "How does the transcript distinguish between people who use routine as a necessity and someone who actively dislikes routine?",
        "expected": "Some rely on routine for discipline, productivity, punctuality, or structure, while one participant explicitly describes themselves as 'anti-routine' and prefers deciding what to do moment by moment.",
        "key_points": ["anti-routine", "discipline/productivity/punctuality", "moment by moment"]
    },
    {
        "id": "Q8",
        "category": "Semantic Retrieval",
        "question": "Why might breaking an established routine make someone feel psychologically uncomfortable according to the discussion?",
        "expected": "It can make them feel outside their comfort zone, disoriented, as though they have not used the morning effectively, and sometimes even guilty.",
        "key_points": ["comfort zone", "disoriented", "guilty / not used morning effectively"]
    },

    # B. Multi-Hop / Multi-Chunk Reasoning
    {
        "id": "Q9",
        "category": "Multi-Hop Reasoning",
        "question": "How are waking early, productivity, and punctuality connected across the discussion?",
        "expected": "Early or fixed waking times create structure and provide more time to work; for people who need routine, it also helps prevent them from arriving late.",
        "key_points": ["structure", "more time to work", "punctuality / prevent late"]
    },
    {
        "id": "Q10",
        "category": "Multi-Hop Reasoning",
        "question": "How does the transcript connect breakfast with maintaining the rest of the day's schedule?",
        "expected": "One participant says that if meal times start shifting later, everything else goes badly, so they sometimes skip breakfast and move directly to lunch to prevent the schedule from becoming delayed.",
        "key_points": ["shift later", "skip breakfast", "directly to lunch", "schedule"]
    },
    {
        "id": "Q11",
        "category": "Multi-Hop Reasoning",
        "question": "What chain of reasoning explains why one person gets up early specifically to play golf?",
        "expected": "They sometimes play golf in the morning, get up early for it, and then need to work afterward.",
        "key_points": ["play golf in morning", "work afterward"]
    },
    {
        "id": "Q12",
        "category": "Multi-Hop Reasoning",
        "question": "How does one participant's morning routine combine personal relaxation with preparation for work?",
        "expected": "They make coffee, sit on the terrace overlooking a natural park/forest, take some quiet time, then continue with their morning routine and eventually go to the metro/work.",
        "key_points": ["coffee", "terrace / forest / natural park", "quiet time", "work / metro"]
    },
    {
        "id": "Q13",
        "category": "Multi-Hop Reasoning",
        "question": "How does the transcript connect coffee consumption with emotional or functional dependence?",
        "expected": "Several participants describe coffee as essential; one says they cannot live without it, another drinks two cups every morning, and skipping it is described as negatively affecting their life/day.",
        "key_points": ["essential / cannot live without", "two cups", "negatively affecting"]
    },
    {
        "id": "Q14",
        "category": "Multi-Hop Reasoning",
        "question": "How do the morning and evening routines reveal two different approaches to planning?",
        "expected": "In the morning, routines organize preparation for work/day activities; in the evening, one person explicitly writes down the next day's unfinished tasks so the following day is clear.",
        "key_points": ["morning work prep", "evening writes down unfinished tasks"]
    },
    {
        "id": "Q15",
        "category": "Multi-Hop Reasoning",
        "question": "What evidence suggests that routine can be both restrictive and beneficial?",
        "expected": "One participant dislikes routine because they want freedom to decide what to do spontaneously, while others say routine provides discipline, productivity, security, punctuality, and mental order.",
        "key_points": ["restrictive / spontaneity / anti-routine", "beneficial / discipline / productivity / security"]
    },
    {
        "id": "Q16",
        "category": "Multi-Hop Reasoning",
        "question": "How does the transcript connect personality with preference for routine?",
        "expected": "The speakers speculate that personality influences whether someone benefits from routine; they suggest some people may be more creative and less routine-oriented while others may prefer structure, though they acknowledge this is somewhat clichéd/speculative.",
        "key_points": ["personality", "creative vs structure", "cliché / speculative"]
    },

    # C. Hard Numerical / Temporal Questions
    {
        "id": "Q17",
        "category": "Numerical / Temporal",
        "question": "What is the difference between the earliest and latest weekend wake-up times explicitly mentioned?",
        "expected": "3 to 3.5 hours: 6:30 AM is the earliest and 9:45 or 10:00 AM are the latest mentioned weekend wake-up times.",
        "key_points": ["3 hours", "3.5 hours", "6:30", "9:45", "10:00"]
    },
    {
        "id": "Q18",
        "category": "Numerical / Temporal",
        "question": "Which person had the earliest stated weekday wake-up time, and why did they wake that early?",
        "expected": "One participant wakes at 5:00–5:30 because they train and also go to work / need to start work very early.",
        "key_points": ["5:00", "5:30", "train", "work"]
    },
    {
        "id": "Q19",
        "category": "Numerical / Temporal",
        "question": "If someone leaves home at exactly 7:20 and spends 40 minutes on the metro, what arrival time does the transcript imply?",
        "expected": "8:00 AM.",
        "key_points": ["8:00", "8:00 AM"]
    },
    {
        "id": "Q20",
        "category": "Numerical / Temporal",
        "question": "How much earlier does the 5:00 AM wake-up occur compared with the person who normally wakes at 8:00–8:30?",
        "expected": "3 to 3.5 hours earlier.",
        "key_points": ["3 to 3.5 hours", "3 hours"]
    },
    {
        "id": "Q21",
        "category": "Numerical / Temporal",
        "question": "What sequence of times is associated with the person whose routine involves the metro commute?",
        "expected": "Wake around 6:00–6:15 → spend about an hour preparing → leave at exactly 7:20 → 40-minute metro journey → arrive at work at 8:00.",
        "key_points": ["6:00", "6:15", "prepare", "7:20", "40 min", "8:00"]
    },
    {
        "id": "Q22",
        "category": "Numerical / Temporal",
        "question": "What alarm times does one participant mention checking before going to sleep?",
        "expected": "8:00, 8:05, and 8:15.",
        "key_points": ["8:00", "8:05", "8:15"]
    },

    # D. Contradiction / Distractor Resistance
    {
        "id": "Q23",
        "category": "Contradiction Resistance",
        "question": "Did everyone interviewed consider having a fixed routine important? Explain using contrasting evidence.",
        "expected": "No. One person explicitly says they are 'anti-routine' and would prefer having no routine, while others describe routine as important for discipline, productivity, punctuality, mental order, or security.",
        "key_points": ["No", "anti-routine", "others"]
    },
    {
        "id": "Q24",
        "category": "Contradiction Resistance",
        "question": "Is the transcript's discussion of routine presented as an established scientific conclusion about personality?",
        "expected": "No. The speakers speculate that personality may influence routine preferences and explicitly acknowledge that the idea may be clichéd.",
        "key_points": ["No", "speculate", "cliché"]
    },
    {
        "id": "Q25",
        "category": "Contradiction Resistance",
        "question": "Did the person who described themselves as anti-routine say they were unable to work from home?",
        "expected": "No. They specifically say they can work from home and therefore their work pattern varies between home, office, client visits, and projects.",
        "key_points": ["No", "can work from home"]
    },
    {
        "id": "Q26",
        "category": "Contradiction Resistance",
        "question": "Was the person who woke at 7:00 necessarily waking that early because of work?",
        "expected": "No. The transcript says they had a stable routine even though it was a holiday.",
        "key_points": ["No", "holiday", "established routine"]
    },
    {
        "id": "Q27",
        "category": "Contradiction Resistance",
        "question": "Did the participant who exercises early say that exercising was the only reason they woke early?",
        "expected": "No. They say they train and also go to work; another participant discusses getting up early for golf and then working.",
        "key_points": ["No", "train", "work"]
    },
    {
        "id": "Q28",
        "category": "Contradiction Resistance",
        "question": "Does the transcript say that everyone drinks the same type of coffee?",
        "expected": "No. Preferences include American-style coffee, espresso, coffee with milk, and coffee prepared with an Italian moka pot.",
        "key_points": ["No", "different types", "American", "espresso", "milk", "moka"]
    },

    # E. Cross-Chunk Synthesis
    {
        "id": "Q29",
        "category": "Cross-Chunk Synthesis",
        "question": "What are the different purposes for which participants use their morning time, and how do these purposes vary?",
        "expected": "They use mornings for work preparation, commuting, exercise/training, golf, swimming, English classes, meditation, checking the weather/news, breakfast, coffee, and quiet personal time.",
        "key_points": ["work", "exercise", "training", "golf", "meditation", "coffee", "breakfast", "commute"]
    },
    {
        "id": "Q30",
        "category": "Cross-Chunk Synthesis",
        "question": "How does the transcript show that routines can be adapted rather than followed rigidly?",
        "expected": "Examples include someone changing their morning for a race, someone getting up early for golf, someone varying breakfast, someone occasionally working from home or visiting clients, and someone abandoning breakfast and moving directly to lunch when they wake late.",
        "key_points": ["race", "golf", "working from home", "skip breakfast", "lunch"]
    },
    {
        "id": "Q31",
        "category": "Cross-Chunk Synthesis",
        "question": "Compare the motivations for early rising among at least three different participants.",
        "expected": "One wakes early because of work/commuting, another because of training plus work, another because of a race, another because of golf, while another maintains an established routine even on holidays.",
        "key_points": ["work", "training", "race", "golf", "routine on holidays"]
    },
    {
        "id": "Q32",
        "category": "Cross-Chunk Synthesis",
        "question": "What common theme links the participant who writes down tomorrow's tasks and the participant who checks multiple alarms before sleeping?",
        "expected": "Both use nighttime preparation to make the following day more organized/predictable.",
        "key_points": ["nighttime preparation", "organized", "predictable"]
    },
    {
        "id": "Q33",
        "category": "Cross-Chunk Synthesis",
        "question": "What common principle connects routine, preparing a bag the night before, writing tomorrow's tasks down, and checking alarms?",
        "expected": "Preparing in advance reduces uncertainty and makes the next day easier to manage.",
        "key_points": ["advance preparation", "reduces uncertainty", "easier to manage"]
    },
    {
        "id": "Q34",
        "category": "Cross-Chunk Synthesis",
        "question": "How does the transcript contrast intentional preparation before sleep with potentially disruptive phone use?",
        "expected": "Some participants prepare for the next day by organizing the kitchen, writing tasks, or checking alarms, while another admits using the phone despite knowing blue light may interfere with sleep.",
        "key_points": ["organizing", "writing", "alarms", "phone", "blue light", "sleep"]
    },

    # F. Speaker Attribution
    {
        "id": "Q35",
        "category": "Speaker Attribution",
        "question": "Who introduces the idea that routine may depend on personality, and what qualification do they make?",
        "expected": "Speaker 2 introduces the idea, suggesting personality may influence routine preference; they acknowledge that the creative-versus-scientific distinction may be a cliché.",
        "key_points": ["Speaker 2", "personality", "cliché"]
    },
    {
        "id": "Q36",
        "category": "Speaker Attribution",
        "question": "Who describes themselves explicitly as 'anti-routine,' and what lifestyle would they prefer?",
        "expected": "Speaker 2; they say they would prefer being able to do whatever they feel like at each moment and wake at different times each day.",
        "key_points": ["Speaker 2", "whatever they feel like", "different times"]
    },
    {
        "id": "Q37",
        "category": "Speaker Attribution",
        "question": "Who explains that routine can provide a kind of 'mental order,' and what benefit do they associate with getting up early?",
        "expected": "Speaker 2; they associate routine with mental order/security and say getting up early makes them feel more productive because they have more hours available to work.",
        "key_points": ["Speaker 2", "mental order", "productive", "more hours"]
    },
    {
        "id": "Q38",
        "category": "Speaker Attribution",
        "question": "Who discusses the blue-light problem associated with using a phone before bed, and why do they continue using it?",
        "expected": "Speaker 2; they know blue light can keep parts of the brain active before sleep, acknowledge they shouldn't use the phone, but admit they still do.",
        "key_points": ["Speaker 2", "blue light", "keep brain active", "still use it"]
    },

    # G. Negative / Unanswerable Questions
    {
        "id": "Q39",
        "category": "Negative / Trick",
        "question": "What exact number of minutes does the transcript say the participant spends meditating every morning?",
        "expected": "Approximately 10 minutes.",
        "key_points": ["10 minutes", "10 min", "diez minutos"]
    },
    {
        "id": "Q40",
        "category": "Negative / Trick",
        "question": "What exact number of cups of coffee does the participant who says 'Sin café no puedo vivir' drink every morning?",
        "expected": "The transcript does not specify how many cups that particular participant drinks. Another participant separately says they drink two cups every morning.",
        "key_points": ["not specified", "does not say", "separate participant drinks two cups"]
    },

    # H. Killer Robustness Questions
    {
        "id": "Q41",
        "category": "Killer Questions",
        "question": "A participant says they wake early because of work, while another says they wake early because of exercise. Are these statements describing the same person? Explain.",
        "expected": "No. They refer to different interviewees.",
        "key_points": ["No", "different interviewees", "different persons"]
    },
    {
        "id": "Q42",
        "category": "Killer Questions",
        "question": "Which participant's coffee habit is explicitly associated with sitting outside and looking at a natural environment?",
        "expected": "The participant who prepares coffee and sits on the terrace looking toward the forest/natural park.",
        "key_points": ["terrace", "forest", "natural park"]
    },
    {
        "id": "Q43",
        "category": "Killer Questions",
        "question": "Did the person who says they are 'anti-routine' nevertheless acknowledge any benefit of routine?",
        "expected": "Yes. Later they say routine can be important for discipline when pursuing a goal over a period of months.",
        "key_points": ["Yes", "discipline", "goal"]
    },
    {
        "id": "Q44",
        "category": "Killer Questions",
        "question": "What does the transcript imply about the relationship between sleeping late and meal timing?",
        "expected": "One participant tries not to let meal times shift when they wake late; if they wake very late, they may skip breakfast and go directly to lunch.",
        "key_points": ["skip breakfast", "directly to lunch", "prevent meal shifting"]
    },
    {
        "id": "Q45",
        "category": "Killer Questions",
        "question": "Which statement is better supported: 'Routine always improves productivity' or 'Routine can improve productivity for some people'?",
        "expected": "The second. The transcript gives individual opinions and explicitly presents routine preference as dependent on the person.",
        "key_points": ["Routine can improve productivity for some people", "second", "dependent on the person"]
    },
    {
        "id": "Q46",
        "category": "Killer Questions",
        "question": "What is the earliest time mentioned in the entire transcript, and what context does it occur in?",
        "expected": "5:00 AM, in the discussion of someone waking early because they train and work.",
        "key_points": ["5:00", "5:00 AM", "train and work"]
    },
    {
        "id": "Q47",
        "category": "Killer Questions",
        "question": "What is the latest wake-up time explicitly mentioned, and why was that person able to sleep that late?",
        "expected": "10:00 AM; it was Saturday/a weekend and the person could sleep in.",
        "key_points": ["10:00", "10:00 AM", "Saturday", "weekend"]
    },
    {
        "id": "Q48",
        "category": "Killer Questions",
        "question": "Did the transcript establish that creative people are less routine-oriented than scientific people?",
        "expected": "No. The speakers speculate about that possibility and explicitly frame it as potentially cliché; it is not established as fact.",
        "key_points": ["No", "speculate", "cliché"]
    },
    {
        "id": "Q49",
        "category": "Killer Questions",
        "question": "What are three different examples of people preparing for the next day before going to sleep?",
        "expected": "Examples include preparing a bag the night before, writing down pending tasks for the next day, and checking that multiple alarms are correctly set.",
        "key_points": ["bag", "writing tasks", "alarms"]
    },
    {
        "id": "Q50",
        "category": "Killer Questions",
        "question": "What is the strongest evidence that the transcript does not portray routine as universally desirable?",
        "expected": "One participant explicitly says they are 'anti-routine,' wishes they could have no routine, and prefers deciding what to do spontaneously.",
        "key_points": ["anti-routine", "no routine", "spontaneously"]
    }
]


def load_chunks():
    transcript_file = Path("data/transcripts/JOB-571EFF4AD742_FILE-4AA4674CFF33_diarized.txt")
    if not transcript_file.exists():
        raise FileNotFoundError(f"Transcript file not found: {transcript_file}")
    
    lines = transcript_file.read_text(encoding="utf-8").strip().split("\n")
    segments = []
    pattern = re.compile(r"\[(\d+):(\d+)\]\s+([^:]+):\s+(.*)")
    for line in lines:
        m = pattern.match(line)
        if m:
            mins, secs, speaker, text = m.groups()
            start_sec = int(mins) * 60 + int(secs)
            segments.append({
                "speaker": speaker.strip(),
                "text": text.strip(),
                "start_time": float(start_sec),
                "end_time": float(start_sec + 4)
            })
    
    chunks = create_sliding_window_chunks(segments, window_size=3, step=2)
    texts = [c["text"] for c in chunks]
    print(f"Generating BAAI/bge-m3 embeddings for {len(chunks)} sliding window chunks...")
    embeddings = get_embeddings_batch(texts)
    for i, c in enumerate(chunks):
        c["embedding"] = np.array(embeddings[i], dtype=np.float32)
    print(f"Successfully generated {len(chunks)} multilingual chunk embeddings (1024-dim).")
    return chunks, "\n".join(lines)


def retrieve_and_rerank(query: str, chunks: list[dict[str, Any]], top_k: int = 8) -> list[dict[str, Any]]:
    q_vec = np.array(get_embedding(query), dtype=np.float32)
    
    candidates = []
    for c in chunks:
        c_vec = c["embedding"]
        sim = float(np.dot(q_vec, c_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(c_vec) + 1e-9))
        c_copy = dict(c)
        c_copy["similarity"] = sim
        candidates.append(c_copy)
    
    candidates.sort(key=lambda x: x["similarity"], reverse=True)
    candidate_pool = candidates[:20]
    
    reranked = rerank_chunks(query, candidate_pool, top_k=top_k)
    return reranked


def query_qwen(prompt: str, context_str: str) -> str:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
        "User-Agent": "ClarityAI/1.0",
    }
    system_prompt = (
        "You are an expert multilingual AI assistant answering questions strictly grounded in the provided audio transcript context.\n"
        "CROSS-LINGUAL RULES:\n"
        "1. Answer clearly, directly, and accurately in English based on the provided Spanish audio transcript context.\n"
        "2. Reference relevant timestamps [mm:ss] and speakers (e.g. Speaker 1, Speaker 2) where appropriate.\n"
        "3. If information is not in the transcript, state clearly that it is not specified. Do not invent facts or mix up speakers.\n"
        "4. Be precise on numbers, times, and nuances."
    )
    user_message = (
        f"CONTEXT (Spanish Audio Transcript):\n"
        f"---\n{context_str}\n---\n\n"
        f"QUESTION: {prompt}"
    )
    payload_data = {
        "model": "qwen/qwen3.8-27b",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.1,
    }
    
    models = ["qwen/qwen3.8-27b", "qwen-2.5-32b-instruct", "qwen/qwen-2.5-72b-instruct", "openai/gpt-oss-120b"]
    for m in models:
        payload_data["model"] = m
        body = json.dumps(payload_data).encode("utf-8")
        req = request.Request(url, data=body, headers=headers, method="POST")
        for attempt in range(1, 4):
            try:
                with request.urlopen(req, context=ssl.create_default_context(), timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    ans = data["choices"][0]["message"]["content"]
                    ans = re.sub(r'<think>.*?</think>', '', ans, flags=re.DOTALL).strip()
                    return ans
            except Exception as e:
                time.sleep(1.5 * attempt)
    return "Error generating response."


def evaluate_response(gen_ans: str, expected_ans: str, key_points: list[str]) -> tuple[bool, float, str]:
    lower_gen = gen_ans.lower()
    matched = 0
    for kp in key_points:
        kp_clean = kp.lower().replace("/", " ").replace("-", " ")
        words = kp_clean.split()
        if any(w in lower_gen for w in words):
            matched += 1
    
    score = matched / max(len(key_points), 1)
    passed = score >= 0.5 or (len(key_points) == 1 and score > 0)
    return passed, score, gen_ans


def run_benchmark():
    print("=" * 80)
    print("STARTING 50-QUESTION BENCHMARK: BGE-M3 + BGE-RERANKER-V2-M3 + QWEN-3.8-27B")
    print("=" * 80)
    
    chunks, full_transcript = load_chunks()
    results = []
    category_stats = {}
    
    for i, item in enumerate(BENCHMARK_QUESTIONS, 1):
        qid = item["id"]
        cat = item["category"]
        q_text = item["question"]
        expected = item["expected"]
        key_points = item["key_points"]
        
        print(f"\n[{i}/50] Running {qid} ({cat}): '{q_text[:65]}...'", flush=True)
        top_chunks = retrieve_and_rerank(q_text, chunks, top_k=8)
        
        context_blocks = []
        for tc in top_chunks:
            start = tc["start_time"]
            end = tc["end_time"]
            ts = f"[{int(start // 60):02d}:{int(start % 60):02d} - {int(end // 60):02d}:{int(end % 60):02d}]"
            context_blocks.append(f"{ts} ({tc['speaker']}): {tc['text']}")
        context_str = "\n".join(context_blocks)
        
        gen_answer = query_qwen(q_text, context_str)
        passed, score, answer = evaluate_response(gen_answer, expected, key_points)
        
        status_sym = "PASS" if passed else "REVIEW"
        print(f"       Status: {status_sym} (Score: {score*100:.1f}%)", flush=True)
        print(f"       Answer: {gen_answer[:120]}...", flush=True)
        
        if cat not in category_stats:
            category_stats[cat] = {"total": 0, "passed": 0, "scores": []}
        category_stats[cat]["total"] += 1
        if passed:
            category_stats[cat]["passed"] += 1
        category_stats[cat]["scores"].append(score)
        
        results.append({
            "id": qid,
            "category": cat,
            "question": q_text,
            "expected": expected,
            "generated": gen_answer,
            "passed": passed,
            "score": score
        })
        
        # Save incremental progress
        out_file = Path("benchmark_results.json")
        out_file.write_text(json.dumps({
            "in_progress": True,
            "completed": i,
            "total": len(BENCHMARK_QUESTIONS),
            "category_stats": category_stats,
            "details": results
        }, indent=2), encoding="utf-8")
        time.sleep(0.3)
        
    print("\n" + "=" * 80, flush=True)
    print("BENCHMARK EVALUATION SUMMARY REPORT", flush=True)
    print("=" * 80, flush=True)
    total_q = len(results)
    total_passed = sum(1 for r in results if r["passed"])
    overall_accuracy = (total_passed / total_q) * 100
    
    print(f"\nOverall Accuracy: {total_passed}/{total_q} ({overall_accuracy:.1f}%)\n", flush=True)
    print(f"{'Category':<30} | {'Passed':<8} | {'Total':<6} | {'Accuracy':<10} | {'Avg Score':<10}", flush=True)
    print("-" * 75, flush=True)
    for cat, stats in category_stats.items():
        acc = (stats["passed"] / stats["total"]) * 100
        avg_s = (sum(stats["scores"]) / len(stats["scores"])) * 100
        print(f"{cat:<30} | {stats['passed']:<8} | {stats['total']:<6} | {acc:>8.1f}% | {avg_s:>8.1f}%", flush=True)
    
    out_file = Path("benchmark_results.json")
    out_file.write_text(json.dumps({
        "overall_accuracy": overall_accuracy,
        "total_passed": total_passed,
        "total_questions": total_q,
        "category_stats": category_stats,
        "details": results
    }, indent=2), encoding="utf-8")
    print(f"\nFull details saved to: {out_file.resolve()}", flush=True)

if __name__ == "__main__":
    run_benchmark()
