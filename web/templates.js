'use strict';
/* Copy-and-paste script templates. Replace everything in {curly brackets}; the [square bracket] tags are optional. */

const TEMPLATES = [
  {
    id: 'short', name: '40-second Short', info: 'About 100 words, one set, vertical',
    text: `# {Your title as a question, e.g. Why is Santa red?}
{Hook: one surprising sentence that makes people stop scrolling.} [point] [surprised]
Most people think {the common belief}. [shrug]
But that's not the whole story.
{The real answer, in one or two short sentences.} [explain]
{The most surprising detail or twist.} [idea] [amazed]
So next time you {everyday moment}, remember {a one-line takeaway}. [thumbs] [happy]
Follow for more hidden origins! [wave]`,
  },
  {
    id: 'long', name: '6-minute video', info: 'About 900 words, 6 chapters, a new set each',
    text: `# {Video title}
{Cold open: start in the middle of the story with a surprising fact or scene. 2 or 3 sentences.} [point] [surprised]
{Make a promise: what the viewer will find out by the end.} [explain]
Let's find out. [nod]

# {Chapter 1: where it all began}
{Set the scene: the place, the time and the people. About 150 words, in short sentences.} [explain]
{Add one vivid detail people can picture.} [clip: {what to show}]
{End the chapter with a small question that leads into the next one.} [think]

# {Chapter 2: the twist}
{The part most people get wrong. About 150 words.} [shrug]
{The real story, with names and dates.} [explain]
{The surprising evidence.} [idea] [amazed]

# {Chapter 3: how it spread}
{How it travelled or changed over time. About 150 words.} [present] [broll: {footage to show}]
{A funny or strange example.} [laugh]
{A turning point.} [focused]

# {Chapter 4: the dark side}
{The part that shocks people. About 150 words.} [shocked]
{Why it was forgotten or hidden.} [sad]

# {Chapter 5: today}
{How it looks now, and the link to everyday life. About 120 words.} [explain] [happy]
{One fact viewers can repeat to their friends.} [count]

# {Outro}
So {one-sentence recap of the whole story}. [nod]
{Ask a question for the comments.} [think]
If you enjoyed this, subscribe for more hidden origins. See you next time! [wave] [happy]`,
  },
  {
    id: 'list', name: 'Top 5 list', info: 'Countdown, 2 to 3 minutes',
    text: `# {Top 5 things you didn't know about ...}
{Hook: why this list will surprise people.} [point] [excited]

# Number 5: {item}
{Two or three sentences about it.} [count] [explain]

# Number 4: {item}
{Two or three sentences about it.} [count]

# Number 3: {item}
{Two or three sentences about it.} [count] [surprised]

# Number 2: {item}
{Two or three sentences about it.} [count] [amazed]

# Number 1: {item}
{The best one. Build it up, then reveal it.} [celebrate] [excited]
Which one surprised you most? Tell me in the comments! [wave]`,
  },
  {
    id: 'myth', name: 'Myth vs fact', info: 'Bust a popular myth, about 1 minute',
    text: `# {The myth, as a question}
You've probably heard that {the myth}. [point]
It sounds right. [shrug] But it's a *myth*. [shake]
{Where the myth came from.} [explain]
{What really happened, with one piece of proof.} [idea] [focused]
{Why the myth is still so popular.} [laugh]
So now you know the truth. [nod] [cool]
Follow for more myths, busted. [thumbs]`,
  },
];

const AI_PROMPT = `Write a YouTube narration script about: {YOUR TOPIC}
Length: {40 seconds | 6 minutes} (about 150 spoken words per minute).
Channel style: a faceless animated presenter explaining the hidden origins of holidays, traditions and everyday things. Friendly, curious, a little dramatic. Short sentences (under 20 words). Facts must be accurate; say "historians think" when something is uncertain.

Format rules (follow exactly, my software reads them):
- Only narration that will be spoken. No speaker names, no stage directions, no "Scene:" or "Visual:" lines, no emojis.
- Start every chapter with a line beginning with "# " and a short title. A 40-second script has one chapter; a 6-minute script has 5 to 7.
- Put *stars* around one or two key words per chapter to highlight them in the captions.
- After a sentence you may add up to two tags in square brackets to control the animated character. Use only these:
  gestures: [point] [point up] [explain] [open] [think] [wave] [thumbs] [celebrate] [present] [shrug] [facepalm] [clap] [count] [stop] [fist] [dance]
  faces: [happy] [excited] [surprised] [angry] [mad] [tired] [sleepy] [focused] [determined] [sad] [cry] [wink] [love] [amazed] [dizzy] [shocked] [suspicious] [laugh] [confused] [cool]
  moves: [nod] [shake] [bounce] [jump] [look around] [lean] [tilt]
  extras: [idea] (lightbulb), [image: two or three search words] (shows a free picture), [clip: two or three search words] (plays free video footage on the set's screen), [broll: two or three search words] (full-screen video footage), [set: studio|christmas|halloween|history|space|tech|nature|ocean|mystery] (picks the room)
- Put a [clip: ...] or [broll: ...] tag on roughly one sentence in four, describing simple, filmable things (e.g. "rocket launch", "snowy forest", "old city street"), never people's names.
- Use tags on about one sentence in three, where they fit the meaning.
- Open with a strong hook in the first sentence and end with a call to follow or subscribe.

Return only the script.`;
