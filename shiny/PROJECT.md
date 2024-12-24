# Radian - Interactive AI-Assisted Data Analysis Platform

## Overview
Radian is a proof-of-concept web application built with R Shiny that enables interactive data analysis with AI assistance. The platform facilitates direct communication between users and AI agents while maintaining context of the analytical workflow, including executed code and its results.

## Core Features

### 1. Interactive Analysis Sessions
- Users can conduct data analysis through a web interface
- AI agent observes code execution and results in real-time
- Analysis sessions maintain context and history

### 2. AI Agent Integration
- Real-time communication with AI agents
- Agents can:
  - Send messages to users
  - Suggest code snippets
  - Execute code directly
  - Observe and respond to analysis results

### 3. Communication Channels
- Chat-like interface for direct communication
- Code execution window
- Results visualization area

## Technical Architecture

### Frontend
- Built with R Shiny
- Dashboard interface using shinydashboard
- Real-time updates and interactions

### Backend
- FastAPI-based REST API
- Endpoints for:
  - Analysis session management
  - Chat functionality
  - Code execution
  - Message handling

### Data Flow
1. User initiates analysis session
2. User can:
   - Execute code
   - Chat with AI agent
   - Receive suggestions
3. AI agent processes:
   - User messages
   - Code execution results
   - Context from the analysis session

## API Structure
- Analysis endpoints (`/analysis/`)
  - Session management
  - Message handling
  - Code execution
- Chat endpoints (`/chats/`)
  - Chat creation and management
  - Message sending and receiving
  - Status tracking

## User Interface Layout

### Main Working Area
- Split into two main columns:
  - Left column (4/12 width): Communication interface
  - Right column (8/12 width): Analysis workspace

### Analysis Workspace
- Located in right column
- Four-tab structure:
  1. Code Tab
     - REPL-style interface:
       - Code input area at bottom
       - History of executed code and outputs above
       - Each execution pair includes:
         - Input code block (In[n])
         - Output/results block (Out[n])
         - Execution timestamp
         - Visual indicator of execution status
     - Code execution sources:
       - User input (primary style)
       - Agent execution (visually distinct style)
     - IPython-like features:
       - Sequential numbering of executions
       - Syntax highlighting
       - Error display
     - Execution history:
       - Scrollable
       - Preserves formatting
       - Collapsible output sections (planned)
  2. Data Tab
     - Data import interface:
       - File upload control
       - File type selection
       - Optional preview pane:
         - First few rows of data
         - Column names and types
         - Basic statistics
     - Supported file types:
       - CSV
       - Excel
       - [other formats to be specified]
  3. Environment Tab
     - Live view of R environment:
       - List of all defined variables
       - Dataset summaries:
         - Dimensions
         - Column types
         - Memory usage
       - Object types and sizes
       - Searchable/filterable list
     - Similar to RStudio's environment pane
  4. [Reserved for future use]

#### Alternative UI Consideration: Popups vs Tabs
The Data and Environment interfaces could alternatively be implemented as modal popups instead of tabs. Here are the trade-offs:

Tabs Approach (Current):
- Pros:
  - Consistent interface with code tab
  - Easier switching between views
  - Persistent visibility of data/environment state
- Cons:
  - Reduces space available for code/output
  - May be unnecessary when focus is on coding
  - Less screen real estate for data preview

Modal Popup Approach:
- Pros:
  - Maximizes space for code/output
  - Full-screen preview capabilities
  - More flexible layout options
  - Better for occasional use cases
- Cons:
  - Extra clicks required to access
  - Context switch when viewing data/environment
  - May interrupt workflow

Current Recommendation:
- Keep as tabs initially for consistency and simplicity
- Consider adding popup option as alternative view
- Gather user feedback on preferred interaction model

### Communication Interface
- Located in left column
- Two-tab structure:
  1. Chat Tab
     - Direct user-agent communication
     - Message styling:
       - User messages aligned right
       - Agent messages aligned left
       - Different background colors for user/agent
       - Timestamps for all messages
       - Full markdown support including code blocks
     - Scrollable message history
     - Input area at bottom

  2. Monologue Tab
     - Internal agent messages
     - Distinct color scheme from chat messages
     - Same markdown and timestamp support as chat
     - Potential future use:
       - May be hidden from end users
       - Could be restricted to debug/development mode
       - Final visibility status pending decision

## Project Management

### Project Structure
- Each project represents a distinct analysis workflow
- Project components:
  - Name (optional, auto-generated if not provided)
  - Description (optional)
  - Associated AI conversations
  - Code execution history
  - Analysis results
- Projects map to `analysis` objects in the backend API

### Project Interface
- Project selector:
  - Modal dialog triggered by UI control (e.g., button in header)
  - Lists existing projects with names/descriptions
  - Option to create new project
  - Search/filter capabilities (planned)
- Current project indicator:
  - Displays active project name in app header
  - Visual indicator for unsaved changes (planned)
- Default naming scheme:
  - Format: "Analysis_YYYYMMDD_HHMMSS"
  - Example: "Analysis_20240315_143022"

### Project State Management
- Active project state maintained in session
- Auto-save capabilities (planned)
- Project history tracking (planned)

## Security
- OAuth2 authentication
- Tenant-based isolation
- Session management

---
*Note: This is a living document that will be updated as the project specifications evolve.* 