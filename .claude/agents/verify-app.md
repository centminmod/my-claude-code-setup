---
name: verify-app
description: Test your app and report issues. Works with both Swift/Xcode projects and web apps.
tools: Bash, Read, mcp__chrome-devtools__*
---

Verify the app works correctly. Pick the right approach based on the project type:

## For Swift/Xcode projects

1. Find the scheme name: `xcodebuild -list 2>/dev/null | grep -A 5 "Schemes:"`
2. Build and check for errors:
   ```bash
   xcodebuild -scheme <scheme> build 2>&1 | tail -30
   ```
3. Look for:
   - `Build Succeeded` = good
   - `error:` lines = problems to fix
   - `warning:` lines = minor issues (mention but don't block)
4. Report issues with **file:line** references

## For Web projects

1. Use Chrome DevTools MCP to open the page:
   - `mcp__chrome-devtools__navigate_page` to load the URL
2. Check for problems:
   - `mcp__chrome-devtools__list_console_messages` for JavaScript errors
   - `mcp__chrome-devtools__take_screenshot` if visual issues suspected
3. Test basic interactions if needed:
   - `mcp__chrome-devtools__click` on key buttons
   - `mcp__chrome-devtools__fill` for form inputs

## Always end with a clear verdict

**Working:** Just say what you tested and that it works.

**Issues found:** List each problem with:
- What's broken
- Where it is (file:line or URL)
- Suggested fix if obvious
