# Language Learning Chatbot - Specification

## 1. Core Concept

A language learning chatbot where users chat with a customizable AI tutor that corrects grammar inline, explains mistakes in a friendly way, and adapts to all proficiency levels.

## 2. Architecture

- **Frontend:** React (Vite)
- **AI Provider:** OpenCode Go (MiniMax M2.7) or Claude API
- **Voice:** Web Speech API (browser-native, free)
- **State:** React Context + localStorage
- **Styling:** Tailwind CSS

## 3. Key Features

### Core Features
- **Customizable AI Persona** - User sets name, personality, avatar
- **Chat Interface** - Simple messaging UI
- **Correction Flow** - AI explains mistake → user corrects → AI confirms
- **Voice Input** - Speech-to-text for speaking practice
- **Text-to-Speech** - Hear correct pronunciation
- **Role-play Scenarios** - Practice real-world conversations (restaurant, travel, job interview)
- **Translation Mode** - Switch between learning and translate
- **Progress Tracking** - View mistakes over time
- **Vocabulary List** - Save new words
- **Difficulty Settings** - Easy/Medium/Hard corrections

### User Flow
1. User opens app → sees chat with customizable AI tutor
2. User types or speaks a message in target language
3. AI analyzes message for grammar/vocabulary mistakes
4. AI explains mistake in friendly way (not just correction)
5. User tries to correct themselves
6. AI confirms correct or guides again
7. Voice output for pronunciation practice

## 4. UI/UX Design

### Layout
- Single page app with chat as main focus
- Left sidebar: vocabulary list, progress stats
- Right sidebar: settings, persona customization (collapsible)
- Top bar: current mode (learning/translate), difficulty indicator
- Bottom: chat input with voice input button

### Visual Style
- Clean, friendly, educational feel
- Warm colors (approachable, not corporate)
- Clear distinction between user messages and AI responses
- Grammar mistakes highlighted with subtle indicators

### Responsive
- Mobile-first design
- Works on tablet and desktop

## 5. Data Storage

- **localStorage:** Persona settings, vocabulary list, progress stats, preferences
- **Session:** Current chat history (not persisted between sessions by default)

## 6. API Integration

- OpenCode Go API for AI responses (MiniMax M2.7)
- Web Speech API for TTS/STT (browser-native)
- Fallback to Claude API if user provides key

## 7. Success Criteria

- Users can have a conversation in their target language
- Grammar mistakes are caught and explained
- Voice input works for speech practice
- Users can customize their AI tutor's personality
- Role-play scenarios provide realistic practice
- Progress tracking shows improvement over time
- App works on mobile and desktop browsers