# 💻 Code Explainer, Syntax & Design Patterns Guide

This guide breaks down the Python programming techniques, asynchronous mechanics, Discord.py patterns, and architectural decisions used throughout the ArcherSniper codebase.

---

## 1. Asynchronous Mechanics (`async def` & `await`)

### What is a Coroutine?
In Python, functions defined with `def` run synchronously to completion, blocking everything else. Functions defined with `async def` return a **coroutine object**:
```python
async def fetch_section_data(self, course_id: str) -> list[dict]:
    ...
```

### What does `await` do?
`await` pauses execution of the *current coroutine* and yields control back to the event loop until the awaited operation completes:
```python
response = await session.post(url, data=payload)
```
* While waiting for DLSU's server to respond, the CPU is completely free to handle other tasks (e.g. Discord slash commands, heartbeat timers, database writes).

### `asyncio.create_task()`: Non-Blocking Fire-and-Forget
When an event happens (such as a session reconnect or heartbeat log), we want to trigger work in the background without holding up the current function:
```python
asyncio.create_task(self.session_refresher.inject_and_start_keeper(cookies, headers))
```
* `create_task()` schedules the coroutine on the event loop and returns immediately (taking 0ms), allowing the calling function to finish without waiting.

---

## 2. Python Modern Type Hinting (Python 3.10+)

ArcherSniper uses clean, modern Python 3.10+ type annotations throughout:

| Syntax | Example | Meaning |
| :--- | :--- | :--- |
| **Union Type** (`|`) | `headers: dict[str, str] | None` | Variable can be a string dictionary OR `None`. (Replaces legacy `typing.Optional`). |
| **Generic Collections** | `cache: dict[tuple[str, str], int]` | A dictionary mapping a `(course, section)` string tuple to an integer slot count. |
| **Tuple Signatures** | `tuple[int, int]` | Function returns exactly two integers: `(ge_count, college_count)`. |

---

## 3. Discord.py Cog Architecture & Decorators

### What is a Cog?
A **Cog** is a Python class that organizes commands, listeners, and state into distinct functional modules:
* `cogs/admin.py` — Administrative controls, keeper commands, and diagnostics.
* `cogs/student.py` — Public student commands (`!watch`, `!watchlist`, `!search`).
* `cogs/help.py` — Role-aware interactive command guides.

### Decorator Patterns
Decorators (`@...`) wrap a function and modify its behavior:

#### 1. `@commands.hybrid_command`
```python
@commands.hybrid_command(name="watch", description="Watch a course for slot drops.")
async def watch_command(self, ctx: commands.Context, course: str, section: str | None = None):
    ...
```
* Automatically registers the command as **BOTH** a prefix command (`!watch STSWENG`) and a Discord native slash command (`/watch course: STSWENG`).

#### 2. Custom Role Decorator: `@is_admin()`
```python
def is_admin():
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.author.id in ADMIN_USER_IDS:
            return True
        if ctx.author.guild_permissions.administrator:
            return True
        return any(r.name == ADMIN_ROLE_NAME for r in ctx.author.roles)
    return commands.check(predicate)
```
* Applied above sensitive commands (`@is_admin()`).
* If a non-admin runs the command, Discord.py halts execution immediately before the function body ever executes.

---

## 4. Discord Interactive UI Components

ArcherSniper leverages Discord's modern UI framework (`discord.ui`):

### 1. `discord.ui.Select` (Dropdown Menus)
Used in `!help` to let users select command categories:
```python
class AdminHelpSelect(discord.ui.Select):
    def __init__(self, ...):
        options = [
            discord.SelectOption(label="Engine Controls", value="engine", emoji="⚙️"),
            discord.SelectOption(label="Session Auth", value="auth", emoji="🔑"),
        ]
        super().__init__(placeholder="Select a category...", options=options)

    async def callback(self, interaction: discord.Interaction):
        # Triggered when user selects an item
        selected = self.values[0]
        await interaction.response.edit_message(embed=new_embed)
```

### 2. `discord.ui.Button` (Clickable Pagination & Links)
Used in `!courses`, `!sweep`, and `!help`:
```python
self.add_item(discord.ui.Button(label="CourseFinder", url="https://archershub.dlsu.edu.ph/CourseFinder/", emoji="🎯"))
```
* Link buttons open URLs directly in the user's browser without bot roundtrips.

---

## 5. SQLite Context Managers & Parameterized Queries

### Preventing SQL Injection
Every query in `database.py` uses parameterized queries with `?` placeholders:
```python
# ✅ SAFE:
cursor.execute("SELECT * FROM monitored_courses WHERE course_code = ?", (course_code,))

# ❌ NEVER USED (Vulnerable to SQL Injection):
# cursor.execute(f"SELECT * FROM monitored_courses WHERE course_code = '{course_code}'")
```

### Safe Context Managers
Database connections are managed via Python context managers:
```python
async with self.connect() as conn:
    cursor = conn.cursor()
    cursor.execute(...)
    conn.commit()
```
* Guarantees connections and cursors are cleanly closed and uncommitted transactions rolled back if an exception occurs.
