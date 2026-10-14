# The Ticket Counter: dashboard design

**Name:** *The Ticket Counter* (Campus Customs). It keeps the deli theme (you take a ticket at a deli counter) while saying what the board is for: handing support tickets to the agent team and getting them back resolved. I dropped the earlier "Campus Customs Deli" because it read as a sandwich shop.

**Concept:** a New York deli counter. You hand your ticket over the counter, the staff work it, and the order comes back stamped. Everything on screen is something you'd find at that counter, so the page feels like one place, not a pile of effects.

## Layout (three zones, read left to right like the order's journey)
| Zone | What it is | Why |
|---|---|---|
| **Left: the order rail** | Tickets 101–103 as paper order slips clipped to a steel rail, each tilted slightly. Each has a big "No. 101" number, the requester, the subject, a status chip, and a green **"Hand it over the counter"** button. | You pick an order and hand it over, which literally starts the run. One run at a time, so the other buttons grey out while one is going. |
| **Center: behind the counter** | Five staff **stations**, a **pass-through window** (delegation trail), an **order pad** (the live event feed, newest last), and the **ORDER UP slip** once the run finishes. | You watch the work happen in the middle of the screen. |
| **Right: the till** | A brass **cash register** with rolling digits, a **receipt tape** below it, and the **manager's desk** where prepared slips wait for a stamp. | Money and approvals sit together, where the manager stands. |
| **Header: the awning** | A navy shop sign with a maroon-and-cream scalloped awning, a red **NOW SERVING** number, a "Store manager" name field (Ms. Lachman), a bell toggle, and **Start a new shift**. | The shop's identity, plus the global controls. |

At 1280px the till drops below the rail and counter, so nothing gets squeezed.

## How the agents read differently
Each agent is a staff member with their own station color (a thick apron-colored top band), a hand-drawn badge, and a "HELLO, MY NAME IS" sticker:

| Staff | Agent | Color | Badge | Voice |
|---|---|---|---|---|
| **SAL** | Boss | navy | the order spike | "Order in!" / "Order up." |
| **ROSIE** | Inventory | deli green | stock crate | "Lemme check the back." |
| **MORT** | Accounting | maroon | ledger + gold coin | "Per the books…" / "Numbers don't lie." |
| **GUS** | Facilities | brass brown | building key | "Building's my beat." |
| **DOTTIE** | Customer Service | slate/silver | counter phone | "Hon, I'll write 'em something nice." |

- **Speech bubbles:** raw tool calls are translated into counter talk. For example, `check_stock` becomes "Checked the shelf: 8 on hand, short 12", and `prepare_payment` becomes "Wrote up a payment slip for the manager: slip #1 on the spike".
- **Station states:** the label (*At the station / Working… / Waiting on MORT / Done / Trouble*) and a gold glow show who's busy at a glance. Agents that weren't needed stay dimmed at "Wiping down the counter."
- **Delegation:** shown as slips in the **pass-through window**. A colored name chip, then "──slip──▶" to the other chip with the question, then "◀──back──" with the answer. Slips slide in as they happen and indent by delegation depth, so the trail of who handed work to whom is clear.

## How resolved tickets and cash show up
- **Resolved:** the ticket gets a red rubber-stamped **FILLED** on the rail, and the summary slip gets a green **ORDER UP** stamp. Before the manager has decided everything, it reads **AWAITING STAMP** instead. The summary lists Sal's call, the plain-English decision, each staff member's tools and answer, who passed slips to whom, who stayed at their station, and exactly what the manager must approve.
- **Approvals:** each pending slip on the manager's desk has **APPROVE** (green) and **VOID** (red outline) buttons. The result lands as a stamp (**PAID**, **APPROVED** or **VOID**) with a quick "thunk" animation.
- **Cash:** the register window shows the checking balance as odometer digits that roll down over about 2 seconds after a payment, so you see $3,400.00 roll to $1,000.00.
- **Receipt tape:** printed on white till paper with a torn zigzag edge. It shows OPENING, a line per payment ("RENT LEASE 1 −$2,400.00, ok'd by Store manager"), and BALANCE.
- **Refused payment:** the register window flashes red and prints **\*\*\* NO SALE \*\*\***, "The register won't ring this one up," and the backend's exact reason (for example "Not enough cash: checking holds $100.00 but item 1 needs $2,400.00. Nothing was approved or paid").

## Type, color, texture
- **Fonts** (bundled with npm, so they work offline):
  - **Courier Prime** for all body text: a clean typewriter face that stays readable.
  - **Special Elite** (a rougher typewriter) only for headings, ticket numbers, name tags and stamps.
  - Stamps also run through an SVG roughness filter, so the ink looks pressed, not printed.
- **Colors:**
  - Walls: subway tile in muted deli green, drawn with CSS grout lines.
  - Paper: cream and butcher-paper slips with an SVG paper-grain texture.
  - Ink: maroon and navy.
  - Trim: gold (register, crest, focus rings) and silver (rail, clips, NOW SERVING frame).
  - Every text color pair is at least **5.4:1 contrast** (checked; body ink is 13.7:1).
- **Graphics:** all hand-made in SVG or CSS. That covers the perforated slip edges (a CSS mask), the scalloped awning, the crest (a sandwich with "EST. 1701"), the five badges, the register and its keys, the receipt tear, and the stamps. There are no image files.

## Touches that make it fun
- **NOW SERVING** shows the ticket being worked in glowing red digits.
- **Counter bell:** synthesized with Web Audio (no sound file). It's off by default, toggled from the header, and dings on hand-over, on "order up", and on a paid approval.
- **Start a new shift** is the reset. It asks first, in a slip-shaped dialog that explains exactly what's restored and that the audit trail is kept.
- **Store manager** is a name field, filled in as Ms. Lachman; that name is what's recorded as the approver.
- The register's round keys run 1 to 9, left to right, like a real adding machine row.

## Graceful states
- **Loading:** "Opening the shop…"
- **Backend down:** after 3 failed polls in a row (not on one slow reply), a red note floats in the corner: "Back office isn't answering… still retrying." All notices float over the page, so nothing jumps.
- **Empty states:** "The counter's quiet.", "Nothing on the spike.", "No slips passed yet."
- **Long runs:** a live timer. After 45 seconds it adds "Big order, still going. Limits keep it from running forever."
- **Failed runs:** a plain message ("The model service had a hiccup… hand the ticket over again"), with the raw error in a tooltip.
- **Reduced motion:** honored; all animations switch off.
