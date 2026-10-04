# Acceptance criteria — FitFindr

Five criteria that say what "working" means for this agent, written in unit 3
**before** any results existed.

An acceptance criterion names a target: a number, a count, a rate, or something
a person could plainly observe. *"The agent handles errors"* is an opinion.
*"When search returns nothing, the agent stops before calling the second tool,
in 5 of 5 tries"* is a criterion.

Under each one, write a sentence or two on **why that target** and not a
stricter one. A reason that says something about your tools, your loop, or the
data earns credit; *"80% seemed reasonable"* does not.

> Missing your own targets next unit costs you nothing. Setting a target so
> easy you can't miss it does.

**Two are written for you. You write three.**

---

## 1. A matching query completes all three tools

Given a query that matches at least one listing, the agent completes all three
tool calls and returns a fit card — in at least 4 of 5 tries.

**Why this target:**
I chose 4 out of 5 because the search uses keyword matching, so some search phrases might not find a listing even when a similar item exists. Requiring 5 out of 5 would be too strict because different wording can affect the search results.

---

## 2. An impossible query stops before the second tool

Given a query that matches no listings, the agent stops before calling
`suggest_outfit` and returns a message naming what to change — 5 of 5 tries.

**Why this target:**
I chose 5 out of 5 because the agent has a specific condition that checks whether the search returned any results. If the list is empty, the loop should stop instead of calling the next tool. This is a predictable part of the agent's logic.

---

## 3. The selected item is passed correctly between tools
When search_listings finds an item, the same item is passed to suggest_outfit through the session state: the `id` of `session["selected_item"]` equals the `id` of the first item in `session["search_results"]` and of the item suggest_outfit received, and the price in the fit card equals `session["selected_item"]["price"]` — in 5 out of 5 tries.

**Why this target:**

I chose 5 out of 5 because the session state is designed to keep the selected listing consistent as it moves between the three tools. The search results and selected item are stored in the session dictionary, so the same item should be passed to suggest_outfit every time. Checking the item ID and price makes it possible to verify that the tools are using the same listing rather than a different result.

---

## 4. The fit card includes the important item details
Running the same matching query 5 times (e.g. 'vintage graphic tee under $30'), at least 4 of the 5 fit cards include at least one distinctive word from the selected item's title (e.g. "tee"), the exact price (e.g. "$18"), and the platform name (e.g. "depop", in any capitalization).


**Why this target:**
I chose 4 out of 5 because the fit card uses Gemini, which can generate different responses each time. The card should still include the important shopping information, even if the wording changes.


---

## 5. Search results stay within the user's budget
When a user enters a maximum price, every returned listing must be at or below that price — in 5 out of 5 tries.


**Why this target:**
I chose 5 out of 5 because search_listings uses a price filter to remove items that exceed the user's budget. This is a basic requirement for the shopping agent and should work consistently without depending on the AI model.


---

<!-- ─────────────────────────────────────────────────────────────────────────
     UNIT 4 — read this before you change anything above.

     If a criterion turns out to be BROKEN rather than merely unmet, you can
     revise it, and that earns credit. But never delete or edit the original
     line. Add the revision underneath it, like this:

         ## 4. Something about the fit card

         The fit card is different every time.

         **Why this target:** ...

         > **Revised in unit 4:** For 5 different items, the 5 fit cards share
         > no opening sentence.
         >
         > **Why revised:** "different" wasn't checkable — two cards that
         > differed by one word still counted. The new version is something I
         > can actually score.

     That's a revision because the criterion couldn't be MEASURED.

     Lowering a target because you missed it is not a revision, and it costs
     you the point:

         ✗ "I said the empty search stops it 5 of 5 times, but I got 3 of 5,
            so 3 of 5 is more realistic."

     A number you missed stays where it is, gets diagnosed, and gets a fix
     attempted. That's where the points are.
     ───────────────────────────────────────────────────────────────────────── -->
