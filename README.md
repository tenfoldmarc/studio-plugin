# Claude Creator Studio

You film your clips. Claude edits the reel.

This is the plugin for buyers of Claude Creator Studio. The walkthrough videos and support are in your portal: https://portal.tenfoldmarketing.com

## Install in the Claude desktop app

This one install covers Claude Code and Claude Cowork.

1. Open the Claude desktop app.
2. Go to **Customize**, then **Plugins**.
3. Choose **Add**, then **Add marketplace**.
4. Paste this and confirm:

```
tenfoldmarc/studio-plugin
```

5. Find **Claude Creator Studio** in the list and choose **Install**.
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

**Desktop app:** Customize, Plugins, open the Creator Studio source, then **Check for updates**. Turn on **Sync automatically** there and you never have to think about it again.

**Terminal:** each line is one paste.

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
