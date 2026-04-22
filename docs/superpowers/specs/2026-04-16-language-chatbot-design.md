# Language Learning Chatbot - Design Specification

> **Created:** 2026-04-16
> **Status:** Approved

## 1. Core Concept

A language learning chatbot where users chat with a customizable AI tutor that corrects grammar inline, explains mistakes in a friendly way, and adapts to all proficiency levels.

## 2. Architecture

- **Frontend:** React (Vite) with Tailwind CSS
- **AI Provider:** Google Gemini API (user provides own free key)
- **Voice:** Web Speech API (browser-native, free)
- **State:** React Context + localStorage
- **Build:** Vite for fast development and building

## 3. UI/UX Design

### Layout Structure

```
┌─────────────────────────────────────────────────────────┐
│  Top Bar: Logo | Mode (Learning/Translate) | Difficulty │
├────────┬────────────────────────────────┬───────────────┤
│        │                                │               │
│  Left  │      Main Chat Area            │    Right     │
│ Sidebar│                                │   Sidebar    │
│        │   Messages + Corrections       │              │
│ Vocab  │                                │  Settings    │
│ List   │                                │  Persona     │
│        │                                │  Customize   │
│        │                                │               │
├────────┴────────────────────────────────┴───────────────┤
│  Input: Text Field | Voice Button | Send Button          │
└─────────────────────────────────────────────────────────┘
```

### Responsive Breakpoints
- **Mobile:** < 640px - Sidebars hidden, use hamburger menu
- **Tablet:** 640px - 1024px - One sidebar visible
- **Desktop:** > 1024px - Both sidebars visible

### Visual Style
- **Color Palette:**
  - Primary: Warm blue (#4F46E5 / indigo-600)
  - Secondary: Warm amber (#F59E0B / amber-500)
  - Background: Off-white (#F9FAFB)
  - Chat bubbles: User (indigo-100), AI (gray-100)
  - Error/Correction: Red-500 for mistakes, green-500 for correct
- **Typography:** Clean, readable sans-serif (Inter or system fonts)
- **Spacing:** Comfortable, educational feel (not cramped)
- **Animations:** Subtle transitions for message appear, sidebar toggle

### Components
1. **ChatMessage** - User/AI message bubbles with timestamps
2. **CorrectionCard** - Highlighted mistake with explanation
3. **VoiceButton** - Microphone icon with recording state
4. **VocabularyItem** - Word + translation + example sentence
5. **PersonaCard** - Avatar, name, personality description
6. **ScenarioSelector** - Role-play scenario cards

## 4. Data Models

### Persona Settings
```typescript
interface Persona {
  name: string;
  personality: 'friendly' | 'strict' | 'patient' | 'playful';
  avatar: string; // emoji or color
  nativeLanguage: string;
}
```

### Vocabulary Item
```typescript
interface VocabItem {
  id: string;
  word: string;
  translation: string;
  example: string;
  addedAt: number;
  reviewCount: number;
}
```

### Chat Message
```typescript
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  correction?: Correction;
  isCorrectionAttempt?: boolean;
}

interface Correction {
  original: string;
  mistake: string;
  explanation: string;
  correctVersion: string;
}
```

### User Settings
```typescript
interface Settings {
  targetLanguage: string;
  difficulty: 'easy' | 'medium' | 'hard';
  voiceEnabled: boolean;
  mode: 'learning' | 'translate';
}
```

## 5. Key Features

### 5.1 Customizable AI Persona
- User sets: name, personality, avatar (emoji or color)
- Personality affects how corrections are delivered
- Stored in localStorage, persists between sessions

### 5.2 Chat Interface
- Message history with timestamps
- Typing indicator while AI responds
- Auto-scroll to latest message
- Copy message text option

### 5.3 Grammar Correction Flow
- AI analyzes user message for mistakes
- If mistake found: show in separate correction card
- Correction card shows: what was wrong, explanation, correct version
- User can try to correct themselves (new message)
- AI confirms correct or provides more guidance
- TTS plays correct pronunciation

### 5.4 Voice Input
- Web Speech API for speech-to-text
- Push-to-talk or continuous mode
- Visual feedback during recording
- Works in Chrome/Edge/Safari (Firefox limited)

### 5.5 Text-to-Speech
- Read AI responses aloud
- Read corrected sentences for pronunciation
- Adjustable speed
- Language-appropriate voice

### 5.6 Role-play Scenarios
- Predefined scenarios: Restaurant, Travel, Job Interview, Shopping, Doctor
- User selects scenario, AI starts with情境
- Real-world conversation practice
- Scenarios adapt to difficulty level

### 5.7 Translation Mode
- Toggle between learning and translate mode
- In translate mode: user types in any language, AI translates
- Helps with understanding unknown words

### 5.8 Progress Tracking
- Track mistakes over time
- Categories: grammar, vocabulary, pronunciation
- Simple stats: total messages, corrections, words learned
- Visual progress indicator

### 5.9 Vocabulary List
- Add words from chat with one click
- View all saved vocabulary
- Delete words
- Stored in localStorage

### 5.10 Difficulty Settings
- **Easy:** Simple corrections, more hints, basic grammar
- **Medium:** Standard corrections, some explanation
- **Hard:** Subtle errors, minimal hints, complex grammar

## 6. API Integration

### Google Gemini API
- Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent`
- API key: User provides from Google AI Studio (free tier)
- System prompt defines tutor behavior
- Include conversation history for context

### System Prompt (Tutor Persona)
```
You are a friendly language tutor helping a [level] student learn [language].
Your persona: [personality description].
Your task:
1. Have natural conversations in [language]
2. Gently correct mistakes when they occur
3. Explain mistakes in a friendly way
4. Ask follow-up questions to keep conversation going
5. Adapt to difficulty level (easy/medium/hard)

Correction style by difficulty:
- Easy: Point out mistake, give hint, show correct form
- Medium: Explain what's wrong, give correct version
- Hard: Let user figure it out with minimal hints
```

## 7. Page Structure (React Components)

```
src/
├── App.jsx              # Main app with routing
├── components/
│   ├── Chat/
│   │   ├── ChatWindow.jsx
│   │   ├── Message.jsx
│   │   ├── CorrectionCard.jsx
│   │   └── ChatInput.jsx
│   ├── Sidebar/
│   │   ├── LeftSidebar.jsx
│   │   ├── RightSidebar.jsx
│   │   ├── VocabularyList.jsx
│   │   └── ProgressStats.jsx
│   ├── Settings/
│   │   ├── PersonaSettings.jsx
│   │   └── GeneralSettings.jsx
│   └── Common/
│       ├── VoiceButton.jsx
│       ├── ScenarioSelector.jsx
│       └── TopBar.jsx
├── context/
│   ├── ChatContext.jsx
│   ├── SettingsContext.jsx
│   └── VocabularyContext.jsx
├── hooks/
│   ├── useSpeechRecognition.js
│   ├── useSpeechSynthesis.js
│   └── useGemini.js
├── utils/
│   ├── api.js
│   ├── localStorage.js
│   └── helpers.js
└── index.css
```

## 8. localStorage Schema

| Key | Value |
|-----|-------|
| `llc_persona` | Persona object |
| `llc_vocabulary` | Array of VocabItem |
| `llc_settings` | Settings object |
| `llc_progress` | Progress stats object |

## 9. Acceptance Criteria

1. ✓ User can customize AI tutor's name, personality, avatar
2. ✓ Chat messages display correctly with timestamps
3. ✓ Grammar mistakes are detected and explained
4. ✓ User can correct their own mistakes with AI feedback
5. ✓ Voice input works for speech practice (where browser supports)
6. ✓ TTS plays AI responses and corrections
7. ✓ Role-play scenarios provide realistic practice
8. ✓ Translation mode works between languages
9. ✓ Vocabulary list saves and displays words
10. ✓ Progress stats show learning over time
11. ✓ Difficulty settings affect correction style
12. ✓ Settings persist between sessions
13. ✓ Mobile-responsive design works on phone/tablet/desktop