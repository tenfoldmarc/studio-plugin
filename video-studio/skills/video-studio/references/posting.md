# Posting

The buyer says "post it", "post these as trial reels", "schedule this for tomorrow at 6" or "put it on TikTok and
YouTube too". You post it for them through their own Zernio account: Instagram (normal reels or trial reels),
TikTok, YouTube Shorts, Facebook Reels, and Threads, LinkedIn, X, Bluesky or Pinterest when they ask. Now, at a set
time, or a few minutes apart. Everything goes through `scripts/post.py` (standard library, any OS).

Zernio is the service that holds the connection to their accounts. The Studio never sees their Instagram or TikTok
password: they log in on the platform's own page, once.

## Setup (once)

`PY "SK/scripts/post.py" check` tells you where they are:
- `STATUS posting NO KEY`: steps 1 and 2.
- `STATUS posting NO ACCOUNTS` or an account missing: step 3.
- `STATUS posting READY instagram,tiktok`: post.
- `ACCOUNT ... NEEDS RECONNECT`: step 3 for that platform (it refreshes the same account, history kept).

1. **A Zernio account.** Send them to https://zernio.link/marc-andre-cleroux to sign up. Say what it costs before
   they go: the first 2 connected accounts are free with no card (Instagram and TikTok, for example), each one after
   that is $6 a month (YouTube as the third). Profiles are free.
2. **Their key.** At https://zernio.com/dashboard/api-keys they click **Create API key** and copy it. Zernio shows it
   once only. Then save it without it ever appearing in the chat:
   - They copied it: `PY "SK/scripts/post.py" key --clipboard`.
   - They pasted it into the chat anyway: Mac/Linux `PY "SK/scripts/post.py" key <<'EOF'` / the key / `EOF`;
     Windows PowerShell `'<key>' | & PY "SK/scripts/post.py" key`. Then tell them to delete that message if they
     can, and never paste it anywhere else.
   - In a terminal of their own, `PY "SK/scripts/post.py" key` asks for it with a hidden prompt.
   `STATUS key SAVED` means it was checked and works. It lives on this computer only.
3. **Connect each platform** they want to post to, one at a time:
   `PY "SK/scripts/post.py" connect instagram --wait` (IN THE BACKGROUND). It opens a page that says "Creator
   Studio wants to connect to your Instagram"; they click Continue and log in on Instagram's own page. The command
   ends with `STATUS connect DONE instagram @handle` when it shows up. No browser opened? It prints the link: give it
   to them. Before they start, tell them what each platform needs:
   - **Instagram**: a Professional account (Creator or Business). Trial reels and posting from apps only work on
     those. A personal account: Instagram app, Settings, "Account type and tools", "Switch to professional account".
     Free, a minute, nothing is lost.
   - **TikTok**: accept every permission on TikTok's screen. One left unticked and nothing connects.
   - **YouTube**: in Google's account chooser pick the identity that owns the channel (a Brand Account channel: pick
     the Brand Account, not their personal name).
   - **Facebook**: they pick the Page to post to.
4. `check` again: every account says `can post`. Several accounts of one platform (two Instagrams): ask which one is
   for this Studio, then `PY "SK/scripts/post.py" use instagram @handle`.

## Posting

```
1. Know four things: which file(s), which platforms, trial reel or normal, when.
     Missing ones: ask in ONE message ("Instagram as trial reels, and TikTok too? Now, or spread out?").
     First time they post: also ask how they like their captions (or read a few of their posted captions if they
     point you to them), then save that: PY "SK/scripts/post.py" notes "<how they write captions>"
2. PY "SK/scripts/post.py" new "<project>/posting.json" "<file or folder>" ... --platforms instagram,tiktok
       [--trial] [--every 5m] [--start now|"2026-10-21 18:00"]
     one post per file, captions left as WRITE ME. A trial-reels folder skips the trials already posted.
     Or write posting.json yourself (post.py --help has every field).
3. Write every caption in posting.json, in their voice and their caption notes. Different captions for different
     trials (Zernio refuses the exact same video and caption twice in 24 hours, and a different caption is a better
     test anyway). YouTube gets a "title" (100 characters at most, no hashtags).
4. PY "SK/scripts/post.py" plan "<project>/posting.json"
     fix every PROBLEM line, plan again until STATUS plan OK. Nothing is sent by plan.
5. Show them the plan in a few lines (what, where, when, the first line of each caption) and ask for a clear yes.
     TikTok in it: add one line, "Posting to TikTok means you agree to TikTok's Music Usage Confirmation."
6. They said yes: PY "SK/scripts/post.py" run "<project>/posting.json" --yes      IN THE BACKGROUND when it is more
     than one video (each one uploads first)
7. Right-away posts: PY "SK/scripts/post.py" status "<project>/posting.json" --wait, then give them the links.
     Scheduled ones: tell them the times; status any time later says what happened.
```

- `run` sends only what has not gone out yet and never sends a post twice: after a failure, fix it and run again.
- A post in the Studio's `trial-reels/` folder that went to Instagram is marked posted for the variations
  (`variations.py posted`) by itself: it is never made again and new trials stay different from it.
- "Put them in Zernio, I'll post them myself": `run --yes --draft`. They are saved as drafts in Zernio's dashboard and
  nothing goes out. A later `run --yes` posts them for real (the drafts make way).
- "Cancel the ones that haven't gone out": say which, get a yes, `cancel "<plan>" --yes [--item N]`. A post already
  live stays live: they delete it in the app.
- A failed platform: the `FAILED` / `status` line says why and the fix in plain words. Fixed: `retry "<plan>"`.

## Trial reels

A trial reel is shown to people who do not follow them first. `"trial": true` puts it out as one on Instagram;
every other platform in the same post gets it as a normal post (TikTok and YouTube have no trial reels).

- `"graduation": "manual"` (the default): it stays a trial. When one wins, they open it in the Instagram app and tap
  "Share to followers". Best when they post several versions and want to pick the winner themselves.
- `"graduation": "auto"`: Instagram shares it with their followers by itself if it does well in the first 72 hours.
- Several trials of one reel: spread them out, `--every 5m` (one now, the next 5 minutes later, and so on), unless
  they want them at set times.
- Never promise a trial "won't get flagged" or "will go viral". Say what was done.

## Limits worth knowing

- Instagram: 100 posts a day through apps. `plan` reads what is left.
- TikTok caps how many posts an account makes per day through apps. `plan` says when it is reached ("cannot post more
  right now"): post the rest tomorrow, or post fewer to TikTok.
- YouTube: a Short is vertical and 3 minutes or less. Anything else goes up as a normal video (`plan` says so).
- Facebook: a Reel is vertical and 3 to 90 seconds. Anything else posts as a normal video.
- Captions: Instagram and TikTok 2,200 characters, Instagram 30 hashtags at most. `plan` checks them.

## Hard rules

- Never post, schedule or cancel without a clear yes to that exact plan in this chat. A yes covers that plan only.
- Only the platforms they named. Never add one because it is connected.
- Never put the key on a command line, in a file in their project, or in a message. Never print it.
- The cover is the first frame unless they ask (`"cover_ms"`). The Studio's reels open on a settled first frame.

## What the buyer hears

- First time, no key: "I can post this for you. It goes through Zernio, the service that connects to your Instagram
  and TikTok. It's free for your first 2 accounts (a third, like YouTube, is $6 a month). Sign up at
  zernio.link/marc-andre-cleroux, then go to API keys, click Create API key, and copy it. Tell me when it's copied."
- Key saved: "Got it, your key is saved on this computer only. Now let's connect Instagram. A page opens, click
  Continue and log in on Instagram's own page. Your Instagram needs to be a Professional account for trial reels."
- Connected: "Instagram is connected (@handle). Want TikTok and YouTube too?"
- The plan: "Here's the plan: 3 trial reels on Instagram, also on TikTok. Trial 1 goes out now, trial 2 at 6:05,
  trial 3 at 6:10. Captions: [first lines]. Posting to TikTok means you agree to TikTok's Music Usage Confirmation.
  Good to go?"
- Posted: "Trial 1 is live: [links]. Trials 2 and 3 go out at 6:05 and 6:10. They're trial reels, so they show to
  non-followers first. When one wins, open it in Instagram and tap Share to followers."
- A failure: "TikTok refused trial 2: it says the daily limit is reached. Instagram has it. Want me to post it to
  TikTok tomorrow morning?"
