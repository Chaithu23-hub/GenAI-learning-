### Trace 1
**Query:** "What does the First Amendment protect?"  
**Expected:** Detailed answer about religion, speech, press, assembly, petition  
**Actual behavior:** ✅ GOOD — System retrieves correct chunk about First Amendment and explains rights clearly.  
**Failure note:** None — this works well.

---

### Trace 2
**Query:** "Can the government take my property?"  
**Expected:** Explanation of Fifth Amendment Takings Clause (public use + just compensation required)  
**Actual behavior:** ⚠️ PARTIAL — System retrieves Fifth Amendment chunk but answer is shallow. Only mentions "takings" without full legal requirement.  
**Failure note:** Incomplete answer — mentions takings but omits "just compensation" requirement. Generator didn't extract the full legal nuance.

---

### Trace 3
**Query:** "What is the difference between First and Fourth Amendments?"  
**Expected:** Comparison — First (free speech/religion) vs Fourth (unreasonable searches)  
**Actual behavior:** ❌ FAIL — System retrieves only First Amendment chunk, ignores Fourth Amendment entirely. Answer is one-sided.  
**Failure note:** Retrieval failed to fetch multiple relevant documents. Cross-document retrieval broken.

---

### Trace 4
**Query:** "What states can sue in national courts?"  
**Expected:** Explanation of 11th Amendment sovereign immunity limits  
**Actual behavior:** ⚠️ PARTIAL — Retrieved 11th Amendment chunk correctly but explanation is confusing. Doesn't clearly state what states CAN'T do (can't be sued by citizens without consent).  
**Failure note:** Ambiguous generation — legal concept explained backwards or unclear.

---

### Trace 5
**Query:** "When was the Bill of Rights added?"  
**Expected:** "Between 1791-1804" or "First 10 amendments, proposed by First Congress"  
**Actual behavior:** ✅ GOOD — System retrieves correct timeframe and context about James Madison.  
**Failure note:** None — works well.

---

### Trace 6
**Query:** "What is the right to remain silent?"  
**Expected:** Fifth Amendment, right against self-incrimination  
**Actual behavior:** ⚠️ PARTIAL — Retrieved Fifth Amendment chunk correctly but phrasing is legal jargon without practical explanation.  
**Failure note:** Answer is technically correct but uses dense legal language. Lacks plain-English explanation of what this means practically.

---

### Trace 7
**Query:** "Why did the founders create the Second Amendment?"  
**Expected:** Concern about standing armies + need for citizen militia  
**Actual behavior:** ❌ FAIL — System retrieves modern Supreme Court interpretation (Heller, McDonald) but not the historical reasoning from the Founding generation.  
**Failure note:** Retrieval prioritized recent case law over historical context. Missed the actual reasoning in document.

---

### Trace 8
**Query:** "Can I be tried twice for the same crime?"  
**Expected:** Fifth Amendment — double jeopardy clause prevents this  
**Actual behavior:** ⚠️ PARTIAL — Retrieved Fifth Amendment section but answer conflates double jeopardy with other rights. Doesn't cleanly isolate the specific protection.  
**Failure note:** Chunking may have split double jeopardy rule from its context. Generator didn't isolate the relevant protection clearly.

---

### Trace 9
**Query:** "What happened in Chisholm v. Georgia?"  
**Expected:** South Carolina citizen sued Georgia state; Supreme Court said yes (4-1), then 11th Amendment was created in response  
**Actual behavior:** ✅ GOOD — System retrieves the full case description and explains the sequence correctly.  
**Failure note:** None — works well.

---

### Trace 10
**Query:** "How many amendments have been ratified?"  
**Expected:** 27 total amendments  
**Actual behavior:** ✅ GOOD — System retrieves opening statement and correctly answers "27".  
**Failure note:** None — works well.

---

### Trace 11
**Query:** "What did the Reconstruction era amendments accomplish?"  
**Expected:** Abolished slavery (13th), promised freedom/equality (14th), extended vote to African Americans (15th)  
**Actual behavior:** ⚠️ PARTIAL — Retrieved the section naming 13th, 14th, 15th as "Second Founding" but details on WHAT each did are missing.  
**Failure note:** Retrieved metadata about amendments but not detailed explanations of their substance. Summary-level answer when detailed answer needed.

---

### Trace 12
**Query:** "Is there a right to privacy in the Constitution?"  
**Expected:** System should indicate this is NOT directly in document; may reference Fourth Amendment context  
**Actual behavior:** ❌ FAIL — System hallucinates discussion of privacy rights, citing document chunks that don't discuss privacy. Confidence marked as "high" despite out-of-scope nature.  
**Failure note:** Hallucination — generator invented content not in source documents. Out-of-scope confidence incorrectly marked as "high".

---

### Trace 13
**Query:** "amendment about soldiers quartering"  
**Expected:** Third Amendment — protects against forced quartering of soldiers in homes  
**Actual behavior:** ✅ GOOD — Retrieved Third Amendment correctly and explains the connection to British Quartering Act.  
**Failure note:** None — works well.

---

### Trace 14
**Query:** "Why did Anti-Federalists demand the Bill of Rights?"  
**Expected:** Feared large national government would oppress people; wanted key liberties protected  
**Actual behavior:** ⚠️ PARTIAL — Retrieved correct chunk but explanation is terse. Doesn't fully convey the historical tension or why Anti-Federalists were concerned.  
**Failure note:** Shallow contextual explanation. Generator extracted fact but not the underlying reasoning or historical significance.

---

### Trace 15
**Query:** "What powers do states keep under the Constitution?"  
**Expected:** Reserved powers; police power; protection under 10th Amendment  
**Actual behavior:** ⚠️ PARTIAL — Retrieved 10th Amendment chunk but answer oversimplifies. Doesn't clearly distinguish "reserved powers" vs. the national powers granted in Article I.  
**Failure note:** Incomplete legal concept — mentions federalism but doesn't explain the actual distribution of powers.

---

### Trace 16
**Query:** "Can the government search my phone?"  
**Expected:** System should say this is not addressed in the provided documents. Modern tech isn't covered.  
**Actual behavior:** ❌ FAIL — System retrieves Fourth Amendment and attempts to apply it, giving a technically wrong or irrelevant answer about general search warrants.  
**Failure note:** Applied old law to modern context not in documents. Should have marked out-of-scope instead of guessing.

---

### Trace 17
**Query:** "What's a "just compensation" in the Takings Clause?"  
**Expected:** System should acknowledge this is not defined in provided documents. Document says "fair price" but doesn't detail what that means.  
**Actual behavior:** ⚠️ PARTIAL — Retrieved Takings Clause chunk but answer says "fair price" without noting that legal definition of "just compensation" is complex and NOT fully explained in document.  
**Failure note:** Oversimplified complex legal concept. Marked confidence as "high" when document doesn't provide deep definition.

---

### Trace 18
**Query:** "Compare the rights to jury trial in 6th and 7th Amendments."  
**Expected:** Both provide jury trials; 6th = criminal, 7th = civil  
**Actual behavior:** ⚠️ PARTIAL — Retrieved both amendments but explanation is list-like. Doesn't clearly highlight the criminal vs. civil distinction.  
**Failure note:** Retrieved multiple sources but answer structure is poor. Didn't synthesize comparison clearly.

---

### Trace 19
**Query:** "What was the gap between amendments?"  
**Expected:** Multiple gaps: 60 years (12th to 13th), 40+ years (15th to 16th), 3 decades since 1992  
**Actual behavior:** ⚠️ PARTIAL — Retrieved gap information but answer is incomplete. Only mentions one or two gaps, not all of them.  
**Failure note:** Incomplete retrieval — chunks with gap information weren't all fetched. TOP_K=5 too low for multi-faceted question.

---

### Trace 20
**Query:** "What does 'incorporation' mean?"  
**Expected:** Process where 14th Amendment extended Bill of Rights to states (not just national government)  
**Actual behavior:** ❌ FAIL — System retrieves brief mention of "incorporation" in parenthetical but no explanation. Answer is just the parenthetical text.  
**Failure note:** Retrieved footnote/aside instead of substantive content. Chunking strategy puts definitions in poor places. Generator doesn't recognize it's insufficient and marks confidence as "high".


