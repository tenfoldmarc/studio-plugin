# Claude Creator Studio

You film your clips. Claude edits the reel.

This is the plugin for buyers of Claude Creator Studio. The walkthrough videos and support are in your portal: https://portal.tenfoldmarketing.com

## Install in the Claude desktop app

1. Open the Claude desktop app and go to the **Code** tab.
2. Click the **+** next to the message box, then **Plugins**, then **Browse plugins**.
3. Click **Add** in the top right, then **Add marketplace**, then **Add from a repository**.
4. Paste this link and click **Sync**:

```
https://github.com/tenfoldmarc/studio-plugin
```

5. Install **Claude Creator Studio** from the list.
6. Start a new chat and type:

```
/video-studio setup
```

Setup asks two quick questions and downloads what it needs. Give it a few minutes. Then the Studio Picker opens so you can pick your look.

## Install from a terminal instead

Only if you use Claude Code in Terminal (Mac) or PowerShell (Windows). Run these yourself, not inside Claude. Each line is one paste.

```bash
claude plugin marketplace add tenfoldmarc/studio-plugin
```

```bash
claude plugin install video-studio@creator-studio
```

On Windows this route needs [Git for Windows](https://git-scm.com/downloads) installed first.

Then open Claude Code and type `/video-studio setup`.

## Getting updates

Fixes and new effects arrive as updates to this plugin. Your picks and your own style are kept.

**The easy way:** when there is a new version, Claude tells you and asks if you want it. Say yes. You can also say this at any time:

```
update the Studio
```

**From a terminal instead:** each line is one paste.

```bash
claude plugin marketplace update creator-studio
```

```bash
claude plugin update video-studio@creator-studio
```

Start a new chat after an update so Claude loads the new version.

## Help

Email info@tenfoldmarketing.com. Say what you were doing and what happened. A screenshot helps.

---

© Ten Fold Marketing. For buyers of Claude Creator Studio, under the terms you agreed to at purchase. Not affiliated with or endorsed by Anthropic or Instagram.
