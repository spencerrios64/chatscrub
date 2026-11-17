# chatscrub plugin

Remove API keys, emails, phone numbers and other private details from AI chats before you share or archive them.

## What you can ask

- "Scrub the API keys and emails out of these exports" (attach your exports)
- "Make this chat safe to share" (paste or attach the text)
- "Also remove my name and my street" (extra words are removed too)

## What it can't do

It works by pattern, so it only catches things with a recognisable shape: keys, tokens, emails, card numbers, phone numbers and passwords inside links. It cannot know that a word is a name or a secret, so tell Claude those words. Check the result before you publish anything.

Project: https://github.com/spencerrios64/chatscrub

## Install

In Claude Code:

```
/plugin marketplace add spencerrios64/chatscrub
/plugin install chatscrub@chatscrub
```

In the Claude app, download the `plugin` folder as a zip, rename it to `.plugin` and open it in a chat.
