# chatscrub

Remove API keys, emails, phone numbers and other private details from AI chats before
you share or archive them.

**Use it here: https://spencerrios64.github.io/chatscrub/**

It is a single web page (`index.html`) with no dependencies and no server. Your files are
read in your browser and never uploaded. Works on desktop and on Android.

## Use

- **Files:** pick AI export files (`.zip` or `.json`) or plain text files, check the list of
  what was found, and press **Download scrubbed zip**.
- **Pasted text:** paste a chat into the box and copy the scrubbed version.

Each removed item is replaced by a marker such as `[KEY REMOVED]` or `[EMAIL REMOVED]`.
Scrubbed exports keep their original format (ids and dates are left alone), so after
unzipping, their `.json` files still load in chatzip and the other tools.

## What it catches

| Kind | Examples |
| --- | --- |
| API keys and tokens | OpenAI, Anthropic, Google, GitHub, Groq, Slack, AWS, Hugging Face, JWTs, `Bearer` tokens, private key blocks |
| Passwords inside links | `https://user:password@host` |
| Email addresses | |
| Card numbers | 13 to 19 digits that pass the card checksum |
| Phone numbers | 9 to 15 digits, with or without `+`, spaces and dashes |
| IP addresses | off by default, because version numbers look the same |
| Your own words | names, addresses, usernames: anything you type into the list |

## What it can't do

- It works by pattern. It **cannot** know that a word is a name, an address or a password.
  Add those to the word list.
- It can miss keys in formats it doesn't know, and it can occasionally remove a long number
  that wasn't a phone number. Check the result before you publish anything.
- A key that was ever pasted into a chat should be replaced with a new one anyway.
- From an export `.zip` only the chat files are scrubbed and copied; other files in it
  (account details, attachments) are left out of the result.
- Tested on small sample Claude and ChatGPT exports and on plain text.

Part of a family of small tools for AI chats: [chatvault](https://github.com/spencerrios64/chatvault), [chatzip](https://github.com/spencerrios64/chatzip), [chatrelay](https://github.com/spencerrios64/chatrelay), [chatbrief](https://github.com/spencerrios64/chatbrief), [chatscrub](https://github.com/spencerrios64/chatscrub), [chatcompare](https://github.com/spencerrios64/chatcompare), [chatstats](https://github.com/spencerrios64/chatstats) and [promptbank](https://github.com/spencerrios64/promptbank).
