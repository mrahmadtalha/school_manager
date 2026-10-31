# Changelog — School Manager

All notable changes to the **School Manager** product by
**Ahmi software firm** are documented in this file.

---

## Format guide (how to maintain this file)

When you add, remove, fix or improve a feature, record it **immediately**
under the `[Unreleased]` heading using the rules below. When you cut a
release, rename `[Unreleased]` to the new version and date.

**Version numbers** follow semantic versioning, applied to the product:

| Bump | When | Example |
|---|---|---|
| **MAJOR** (1.x.x → 2.0.0) | A new major module, a data-format change that requires migration, or anything that breaks a school's workflow | "Online fee collection" |
| **MINOR** (1.0.x → 1.1.0) | A new feature or a visible improvement to an existing module | "Urdu interface", "SMS fallback" |
| **PATCH** (1.0.0 → 1.0.1) | Bug fixes, small refinements, build/signing changes — no new features | "Fixed receipt numbering gap" |

**Entry rules:**

1. Work happens under `## [Unreleased]` — move entries out only on release.
2. Use exactly these categories, in this order:
   `### Added` · `### Changed` · `### Fixed` · `### Removed` ·
- Term Examinations — the old banner with *Assessment center*, the grey filter box that reloaded the page, and the plain cards are replaced by the same header, summary band, tool bar and cards the Class Tests page uses, so both pages look and work the same way.
- Term Examinations — **page redesigned for non-technical users** (same family as Class Tests and Students): a plain header with the title and one line, the **Class Tests / Term Examinations** switch and the **Add Term Exam** button (administrator only) on the right, then **one summary band**: **term exams in all, results published, exams whose marks are complete, and exams whose marks are still to be entered** (orange while something is waiting, green when nothing is), and a *What to do now* note that points to the next step.
- Term Examinations — **choose how to see your exams: Cards or List**. A *Show exams as* switch changes the page between the cards and a **list with one row per exam** (name with type, status and dates, class, subjects, total marks, a *Marks entered* bar and the buttons). Click a row to open the exam. The choice is remembered in this browser and is the same one used on the Class Tests page.
- Term Examinations — **one clear button per exam**: *Enter Marks* is the main button while marks are missing, *Open* becomes the main button once marks are complete (with *Edit Marks* next to it), and the printer button now has a tooltip *Date sheet*. Each card shows the type, a coloured status (*Scheduled / Ongoing / Published*), dates and session, class, subjects, total marks and a *Marks entered* bar.
- Term Examinations — **find an exam quickly**: a *Find an exam* box, *All Classes*, *All Status* and *All Sessions* menus (the session menu appears only when there is more than one session) and three buttons: *All term exams*, *Marks to enter* and *Marks complete*, each with its count. The page no longer reloads when you change a filter.
- Term Examinations — **your search and filters are remembered** while you open an exam, enter marks and come back; a **Clear filters** button appears while any filter is on. A new browser tab starts fresh.
- Term Examinations — **Urdu**: every new label, sentence and button on the page is translated.
- Tests — new `tests/test_examinations_page_redesign.py` covers the redesigned Term Examinations page (header, summary counts, one action per exam, nothing-waiting state, search and filters, remembered filters, the Cards / List switch and the list rows, Add Term Exam window, empty page and Urdu).
- Class Tests — the big coloured banner at the top is replaced by the same plain header the Students page uses (title and one line on the left, buttons on the right), and the four summary boxes are now one band, so the page looks like the rest of the program. The *What to do now* note now says "press **Enter Marks** on a test" (it works for cards and for the list).
   `### Deprecated` · `### Security`
3. One line per change: **`Module — what changed (for whom)`**.
   Name the module first so readers can scan.
4. Write for school owners, not developers: "Fees — receipts now show the
   class teacher" beats "refactored receipt context builder".
5. Never delete history. The newest version is always at the top.
6. On release: set the version and date, bump `#define MyAppVersion` in
   `installer/SchoolManager.iss`, run `python tools/make_release.py`,
   and note the installer's SHA-256 from `build/release/`.

**Template for a new version:**

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- School Settings — **page redesigned for non-technical users** (same family as Students, Users & Roles and License): a plain header, a *What to do now* note and the same four tabs as a clean segmented bar. Every tab keeps the same forms and fields; what changed is the grouping and the wording.
- School Settings — **General School Info** is split into small titled sections: *School Identity* (name, tagline, logo with the current one shown), *Brand Colors* (two big colour pickers and a "Go back to the standard colors" button), *Contact Details* and *Admission Numbers* (a big switch, the pattern boxes and a live preview). *Students without an Admission No* is its own card and the *Sidebar Preview* stays in view on the right while you scroll.
- School Settings — **Academic Timings** is split into *School Day*, *Attendance Rules*, *Days Off & Holidays* (Saturday and Sunday as big switches, other days, holiday ranges) and *Timetable Periods*; *Grading Scale* explains what the minimum % means with an example.
- School Settings — a **Save bar stays at the bottom of the screen** while you scroll a long form, so you never have to hunt for the Save button.
- School Settings — **Academic Timings uses the full width**: School Day / Attendance Rules and Days Off / Timetable Periods sit side by side on a wide screen, so there is much less scrolling. The Save bar turns amber and says **"You have unsaved changes — press Save."** as soon as you edit something.
- School Settings — **Custom Fields**: a short note explains what they are, and the confusing column names are now *Short name* and *Label on form* (with a tooltip each).
- School Settings — **System Integrations**: the two "Database Protection" and "Backups" cards are merged into one *Backups* card (what a backup is, automatic on / off, latest copy, *Back up now* and the list); *WhatsApp Messaging* has a plain one-line description.
- School Settings — **Urdu**: every new label, sentence and button on the page is translated.
- Tests — new `tests/test_settings_page_redesign.py` covers the redesigned Settings page (header and tabs, every General and Academic field name, custom-field links, merged Backups card, saving still works, Urdu labels).
- Documents — **page redesigned for non-technical users** (same family as Students and Users & Roles): a plain header, a *What to do now* note, a small count band (students, staff, classes) and then two simple questions. **1. What do you want to print?** — three big buttons: *Student ID Cards*, *Staff ID Cards*, *Certificates*. **2. Who is it for?** — *Everyone / A whole class / One student* (staff: *All staff / One teacher*; certificates: *One student / A whole class*). Only the boxes that matter are shown, and a line such as "Prints 28 cards for the whole class." says what you will get before you press Download.
- Documents — **certificate type is now four clear buttons** (Bonafide, Character, School Leaving, Merit) instead of a menu; the page opens on the right tab when you come from a student's report or a teacher link. A friendly message appears if you forget to choose a class, student or teacher.
- Documents — the **fees box** for ID cards and certificates (administrator) is folded under *For the school office* and opens when you follow a link to it; *Recently issued* sits next to it.
- Change Password — the window is clearer: *Your current password*, *New password* and *Type the new password again*, each with a show / hide eye, and **three live ticks** (at least 8 characters, a letter, a number) plus "Both passwords are the same". *Update Password* switches on only when everything is right, so a wrong entry no longer closes the window and shows an error on the dashboard.
- Documents / Change Password — **Urdu**: every new label, sentence and button is translated.
- Tests — new `tests/test_documents_page_redesign.py` covers the redesigned Documents page (what / who questions, unchanged field names and links, opening from a student report or teacher link, fees box for administrators, Change Password window and rules, Urdu labels).
- Software License — **page redesigned for non-technical users** (same family as Students and Users & Roles): a plain header, then **one status band** that says in a sentence whether everything is fine (green / orange / red) with *Licensed to*, *Valid until* (with days left and a progress bar) and the date after which the program only opens. The license ID and key revision are folded under *Technical details*.
- Software License — **three simple steps to renew** (copy this computer's code, send it to your provider, paste the key you get back and press *Activate*), with the code box and the key box together in one card. When the license has ended or is not activated yet, this card comes first.
- Software License — **Included features** are grouped (Finance, Attendance, Security …) with a "3 of 4 features are on" line and a lock on features not in your plan; **WhatsApp messages** show today's and this month's use with a progress bar.
- Software License — **Urdu**: every new label, sentence and button on the page is translated.
- Tests — new `tests/test_license_page_redesign.py` covers the redesigned License page (header and status band, three-step help, key box, folded details, grouped features, activation still works, Urdu labels).
- Users & Roles — **page redesigned for non-technical users** (same family as Students): a plain header with the title and one line, *Activity Log* and *Add User* buttons, a *What to do now* note, and **one summary band** (logins in all, who can sign in and how many are switched off, and a coloured bar showing how many Administrators, Teachers, Parents, Principals, Accountants and Guards you have).
- Users & Roles — **find a person quickly**: a search box (name or username), an *All roles* menu and *Everyone / Can sign in / Switched off* buttons. The list filters instantly without reloading and shows "Showing X of Y people"; a clear button appears while a filter is on.
- Users & Roles — **clearer list**: each person shows a coloured initial, their full name with the username under it (and a *You* tag on your own login), a role tag, who they are connected to (teacher record or children), *Can sign in?*, and the last sign-in in plain local time ("30 Oct 2026, 09:05 AM"). A parent with no child linked is shown in red. Click a row to edit that person. On a phone every person becomes a card, so no buttons hide off the screen.
- Users & Roles — **What can each role do?**: a fold-out guide that explains all six roles in one plain sentence each (roles your plan does not include are marked).
- Users & Roles — **tick-box child picker** for parent logins (with a search box and a "2 children selected" count) replaces the Ctrl+click list. A parent login without a child is stopped with a clear message before the page reloads.
- Users & Roles — **password help**: show / hide eye and a *Suggest* button that makes a strong password (letters and numbers) for you.
- Users & Roles — **Urdu**: every new label, sentence and button on the page is translated.
- Tests — new `tests/test_users_page_redesign.py` covers the redesigned page (header and hint, summary counts, shared windows, row action links, parent without child, tick-box picker, own-login protection, switch-off confirmation, existing actions, Urdu labels).
- Licensing — the vendor dashboard can now switch three more features per school (Data export, Urdu / English switch, Audit log viewer) and switch **user roles** on or off (teacher, accountant, principal/owner, parent; administrator is always on). A switched-off role cannot be created and its users are signed out with a message. The audit log keeps recording even when its viewer is switched off. Keys issued earlier keep every new feature and role switched on.
- Exit Software — the closing page now tries to close its own window (works in an app window; an ordinary browser tab still shows the message).
- Add Student form — Admission No is read-only when automatic numbering is ON (also in the Edit form; the app gives the number and a typed one is ignored). Books and uniform prices are fixed by the class and cannot be typed on the form; the form only chooses what this student takes: books (taking / not taking) and the number of uniform sets (0 to 20, e.g. 2 sets of uniform and 1 set of books). Received-now amount and method stay editable. The Custom Fields heading appears only when a custom field has been created.
- Urdu interface (phase 1) — an English / اردو switch at the bottom of the sidebar (works for every role and is remembered). In Urdu the page turns right-to-left with a proper Urdu font; text you type (names, addresses, class names) is never changed. Covers the daily screens: login, dashboard, students, attendance, fees, admission, classes, teachers and the receipts. Words not translated yet simply stay English. Add wording in app/services/i18n_ur.py. Dashboard cards, the finance overview / insights sentences (with amounts and percentages kept in reading order), month names, the Add Student form hints and its JavaScript labels are translated; English sentences left on a page keep their full stop on the correct side.
- Module — feature description
- Tests — new `tests/test_qr_tab_page.py` covers the redesigned QR Scans tab (list order, chip counts, set-up steps open / folded, teacher view, approval card, closed day).

### Changed
- Users & Roles — Edit, New password and Children now open in **one shared window** for the whole page instead of three windows per user (the page loads faster for schools with many users). Switching a login off now asks "Are you sure?" first and explains that nothing is deleted; wording is plainer ("Switched off", "Can sign in?", "Never signed in").
- Fee Reminders — the billing month is a dropdown of months that still have unpaid fees (plus the current month) instead of a typed box.
- Module — behaviour change description

### Fixed
- Administrator menu: **Users & Roles, School Settings and License** were hidden whenever the license did not include the "Audit log viewer" feature (they sat inside that feature's condition). They now always show for the administrator; only the Audit Log link follows its feature.
- Vendor dashboard: the Premium plan is kept equal to "every feature", so features added after the plan was first saved (Audit log viewer, QR attendance, ...) are no longer left out of new Premium keys. A date typed in "Custom expiry" now always wins over the Validity dropdown (before it was silently ignored unless the dropdown said Custom, so a key could be issued with a different expiry from the one typed).

### Security
- Anything affecting data protection or access control
```

---

## [Unreleased]

### Added
- Sidebar — **menu grouped under small headings** so it is quicker to scan, and **each group can be folded shut** with a click on its heading (the choice is remembered; the group that holds the open page always stays open): *Academics* (Students, Teachers, Classes & Subjects), *Attendance*, *Assessment*, *Documents & Messages*, *Finance* and *System* (Audit Log, Users & Roles, School Settings, License). A heading appears only when at least one link under it is available to the person's role and plan, so there are never empty headings. In the narrow icon-only mode the headings become thin lines between groups.
- Sidebar — **quick find**: a small *Find a page* box at the top of the menu (Ctrl+K or Cmd+K jumps to it). Type a few letters and the menu shows only the matching pages; **Enter** opens the first one, **Esc** clears the box. It is shown to administrators, teachers and accountants and works in Urdu too.
- Sidebar — **the open page is easy to spot**: the highlighted link now has a small coloured bar beside it, and the menu scrolls to the open link (and remembers where you were) when the next page loads, so a long administrator menu no longer jumps back to the top.
- Sidebar — **stays on screen**: on a computer the menu is fixed and scrolls by itself (with a slim scroll bar), so it no longer scrolls away together with a long page. In the phone drawer every link is a bigger tap target.
- Sidebar — **keyboard and screen reader help**: a *Skip to main content* link appears when you press Tab at the top of the page, the open link is announced as the current page, and every link has its name even in icon-only mode. Animations are switched off for people who ask their device for reduced motion.
- Sidebar — **Urdu**: the new headings, the *Find a page* box and the *Skip to main content* link are translated.
- Tests — new `tests/test_sidebar_redesign.py` covers the sidebar (headings for each role and their open / close buttons, quick-find box, no empty headings, exactly one highlighted link on each page, finance pages lighting up their own link, balanced menu markup, a name on every link, Urdu headings, skip link).
- Forgot username / password page — **redesigned to match the new Login page**: your **school logo, name, address and phone** show on the left, and the right side explains recovery in **three plain steps** (send the request code, wait for the reset token, paste the token).
- Forgot username / password page — **easier to use**: a **Copy code** button, a **Send on WhatsApp** button that opens WhatsApp with your request code already written, a big green button that cannot be pressed twice by mistake, and **Show / Hide** on both password boxes in the last step. *Need a new request code?* is tucked away until you need it.
- Forgot username / password page — **Urdu**: every new line, button and message on the page is translated.
- Tests — new `tests/test_recover_page_redesign.py` covers the logo and name, the three steps and the Copy / WhatsApp buttons, Urdu and the wrong-token message.
- Audit Log — **page redesigned for non-technical users** (same family as the Students page): a plain header with one line (*see who did what and when*), the **Export CSV** button, and a *What to do now* note.
- Audit Log — **one summary band**: entries on the list, a colour bar of **Added / Changed / Deleted / Other**, and a red **To check** box that counts failed sign-ins and deleted records and opens them with one click.
- Audit Log — **plain words instead of codes**: actions now read *Added, Changed, Deleted, Signed in, Failed sign-in, Payment received, Cancelled (void), Settings changed…* with a colour for each, in the filter menu as well.
- Audit Log — **find things quickly**: a search box, menus for *what it was about*, *what happened* and *who did it*, and buttons **Any time / Today / Last 7 days / Last 30 days** (the From / To dates still work). The page and the CSV export use the same filters, and a **Clear filters** button appears while any filter is on.
- Audit Log — **See what changed**: each row opens a small table of *Field, Before, After* (for example *Monthly fee 2500 → 3000*) instead of raw text; technical fields such as ids and update times are left out and long changes point to the CSV export.
- Audit Log — **Urdu**: every new label, sentence and button on the page is translated.
- Tests — new `tests/test_audit_page_redesign.py` covers the plain wording and summary, the before / after table, the quick ranges and CSV export, the empty page, Urdu and administrator-only access.
- Login page — **page redesigned for non-technical users**: your **school logo, school name, address and phone** now show on the left (on a phone they sit in a band on top), and a big, clear sign-in form on the right with the plain line *Type your username and password, then press the green button*.
- Login page — **easier typing**: a **Show / Hide** button to see the password you are typing, a yellow **Caps Lock is on** warning, a large green **Sign In** button that cannot be pressed twice by mistake, and the username stays filled in when the password is wrong.
- Login page — if the school has not added a logo yet, a school picture is shown instead; the **starting login (admin / admin123)** hint now appears only while that password has not been changed.
- Login page — **Urdu**: every new line, hint and button on the page is translated, including the wrong-password message.
- Login page — you now land on the page you originally asked for (for example Students) after signing in, instead of always the home page.
- Tests — new `tests/test_login_page_redesign.py` covers the logo and school name, the no-logo picture, the starting-login hint, the kept username, the return to the wanted page and Urdu.
- Class Results — **page redesigned for non-technical users** (same family as Students and Class Tests): a plain header with the title and one line (*see how every student did, write a remark and print the report cards*), the big **All Report Cards PDF** button, and a **More downloads** menu that keeps *Whole class result (PDF)*, *Excel* and *CSV* together instead of four buttons in a row.
- Class Results — **pick the class and the test type in one clear box**. The session and result announcement date show as two small tags with a **Change** button that opens the two boxes only when needed (they are the details printed on the report cards). Changing the class now clears the test type, so you never land on an empty page by mistake.
- Class Results — **one summary band**: students (and number of tests), class average, pass rate (with *7 passed, 3 not passed*, green / orange / red by how well the class did) and the top scorer. A *What to do now* note says how many students did not pass and points to the **Not passed** button; when everyone passed it says so and tells you the report cards are ready.
- Class Results — **find students quickly**: a *Find a student by name or roll no* box, **All students / Passed / Not passed / Absent** buttons with counts (*Absent* appears only when someone was absent), a **Sort by** menu (position, name, roll no, highest or lowest marks) and a **Clear filters** button. The page does not reload, and your search and choice are remembered while you save remarks and come back.
- Class Results — **easier to read marks table**: each student is one clear block (position or medal, name, roll no, father name) that stays in view while you scroll sideways on a phone; marks are soft colour tags by grade, *ABS* stays amber, failed students have a red edge and the top student an amber edge, and the column heads show the subject, the test name and *out of 50*. The header row stays on top while you scroll down a long class.
- Class Results — **grade guide is now correct for your school**: *How grades work* lists the grade scale saved in Settings (before, the A+ / A / B / C / D / F percentages were fixed text and were wrong if the school changed its scale).
- Class Results — **remarks are safer to save**: a changed remark gets an orange edge and a bar at the bottom says *N remarks not saved yet* with a **Save Remarks** button; the browser also warns before you leave the page with unsaved remarks.
- Class Results — **friendly empty pages** with one button each: no classes (*Go to Classes*), no tests for the class (*Go to Class Tests*), no tests of the chosen type (*Show all test types*) and no students in the class (*Go to Students*).
- Class Results — **Urdu**: every new label, sentence, button and message on the page is translated, and numbers, totals and grades keep their left-to-right order inside the Urdu page.
- Tests — new `tests/test_class_results_redesign.py` covers the redesigned Class Results page (header and downloads, summary, student rows and report buttons, the not-passed note and the all-passed note, grade guide from the grading scale, session and date kept, saving remarks, save bar, empty pages and Urdu).

- Class Tests — **page redesigned for non-technical users** (same family as the Students page): a plain header with the title and one line (*make a test, then enter the marks of every student*), and the **Class Tests / Term Examinations** switch with the **Test Categories** and **Add Test** buttons on the right, then **one summary band** with four numbers: **tests in all, tests this month, tests whose marks are complete, and tests whose marks are still to be entered** (orange while something is waiting, green when nothing is), and a *What to do now* note that points to the next step.
- Class Tests — **cards view: one card per test**: the card's top colour follows the test type, and it shows the name, date, class, number of subjects, total marks and a **Marks entered** bar (*No marks yet*, *Marks 12/30 (40%)* or *Marks complete*). Each card has one big button — **Enter Marks** (or **Edit Marks** once finished) — and a small delete button.
- Class Tests — **choose how to see your tests: Cards or List**. A *Show tests as* switch next to the search box changes the page between the cards and a **list with one row per test** (test name with its type and date, class, subjects, total marks, a *Marks entered* bar and the same **Enter Marks / Edit Marks** and delete buttons). Search, class, type and the *All tests / Marks to enter / Marks complete* buttons work the same in both views, and the choice is remembered in this browser.
- Class Tests — **list view is easy to use**: click anywhere on a row to open its marks page, the row's left edge shows the test type colour, and on a phone the less important columns (subjects, total marks) fold away so the name, class, marks status and button stay readable.
- Class Tests — **your search and filters are remembered**: after you press *Enter Marks*, save, and come back to the page (or add / delete a test), the same search, class, type and *All tests / Marks to enter / Marks complete* choice is still there, so you do not have to set them again. A **Clear filters** button appears while any filter is on. A new browser tab starts fresh.
- Class Tests — **Find a test** box, *All Classes* and *All Types* menus, and three buttons: *All tests*, *Marks to enter* and *Marks complete*, each with its count. The empty page now has an **Add Test** button. The Add Test window is titled *Add a Test*.
- Class Tests — **Urdu**: every new label, sentence and button on the page is translated.
- Tests — new `tests/test_tests_page_redesign.py` covers the redesigned Class Tests page (Students-style header, summary counts, one action per row, nothing-waiting state, search and filters, the Cards / List switch and the list rows, add / categories / delete windows still present, empty page and Urdu).
- Teacher Attendance Summary — **page redesigned for non-technical users** (same family as the Attendance Summary page): a plain note under the title, one bar with **This Month / Last Month** buttons and *From / To* dates, and a summary band with **teachers, average attendance (with a coloured bar and the number of school days recorded), teachers who were never absent, and teachers who need attention (below 75%)**. The last box turns red when somebody is below 75% and green when nobody is.
- Teacher Attendance Summary — **totals first, days after**: each teacher's row shows the profile photo (or initials), ID, name and designation / qualification, then the **Attendance %** (green 85% or more, orange 75 to 85%, red below 75%), then **Present, Absent, Late (with total late minutes) and Leave** counts, and only after them the day-by-day boxes (P, A, L, LV) with the weekday and month on top of every date. The teacher's name stays on screen while the days scroll sideways.
- Teacher Attendance Summary — **Find a teacher** box and three buttons: *All teachers*, *Need attention* (only teachers below 75%) and *Never absent*, each with its count. *How to read the boxes* explains the colours in everyday words, and a clear message with a *Take Teacher Attendance* button appears when nothing is saved for the chosen dates. Export (PDF / Excel / CSV) moved into one *Export* menu; *Take Teacher Attendance* and *Student Attendance Summary* stay one click away.
- Teacher Attendance Summary — **Urdu**: every new label, sentence and button on the page is translated.
- Tests — new `tests/test_teacher_attendance_summary_page.py` covers the redesigned Teacher Attendance Summary (period bar, totals before day boxes, rate colours, late minutes, leave, empty states, search and filter buttons, export links, wrong or broken dates and Urdu).
- Attendance Summary — **page redesigned for non-technical users** (same family as the Student Attendance page): a plain note under the title, one bar with the **class** (or *All School Students*), **This Month / Last Month** buttons and *From / To* dates, and a summary band with **students, average attendance (with a coloured bar and the number of school days recorded), students who were never absent, and students who need attention (below 75%)**. The last box turns red when somebody is below 75% and green when nobody is.
- Attendance Summary — **totals first, days after**: each student's row now shows the **Attendance %** (green 85% or more, orange 75 to 85%, red below 75%), then **Present, Absent, Late (with total late minutes) and Leave** counts, and only after them the day-by-day boxes (P, A, L, LV) with the weekday and month on top of every date. The student's name stays on screen while the days scroll sideways.
- Attendance Summary — **Find a student** box and three buttons: *All students*, *Need attention* (only students below 75%) and *Never absent*, each with its count. A plain note says when **no attendance has been saved** for the chosen dates, and *How to read the boxes* explains the colours in everyday words. Export (PDF / Excel / CSV) moved into one *Export* menu; *Take Attendance* and *Teacher Attendance Summary* stay one click away.
- Attendance Summary — **Urdu**: every new label, sentence and button on the page is translated.
- Tests — new `tests/test_attendance_summary_page.py` covers the redesigned Attendance Summary (period bar, totals before day boxes, rate colours, late minutes, leave, nothing-saved note, filters, whole-school view, export links, wrong or broken dates and Urdu).
- Teacher Attendance — **page redesigned for non-technical users** (same family as the Student Attendance page): a short *What to do now* note, a **date bar with Previous day / Next day / Today** buttons, and one summary band with the **number of teachers**, a **coloured bar with live Present / Absent / Late / Leave counts** and a plain **Saved for this day** / **Not Yet Saved** box. Everyone still starts as Present, so only the absent, late or on-leave teachers need a tap.
- Teacher Attendance — **four big status buttons per teacher** (Present green, Absent red, Late amber, Leave grey) instead of small outline buttons; the whole row takes the same colour, the check-in time box appears only for Present / Late, and a saved late arrival shows a clear *Late · 20 min* tag. Each teacher shows the profile photo (or initials), name and designation / qualification.
- Teacher Attendance — **Find a teacher** box (by name or ID), a *Reset* button that undoes this visit's changes, *All Absent* now asks *Mark every teacher as Absent?* before doing it, and when only some teachers were saved, a note names the teachers **not marked yet** with a *Show only these teachers* button.
- Teacher Attendance — the **Save Teacher Attendance** bar stays at the bottom of the screen while the list scrolls and shows "Ready to save: N present · N absent · N late · N on leave". On a phone every teacher becomes one tappable card with full-width status buttons. Export (PDF / Excel / CSV), the *Monthly Summary* link and *All Teachers at Time* stay on the page.
- Teacher Attendance — **Urdu**: every new label, sentence and button on the page is translated.
- Tests — new `tests/test_teacher_attendance_page.py` covers the redesigned Teacher Attendance page (date buttons, unchanged form field names, saved / not-saved box, not-marked-yet note, saved late minutes, saving, empty state, search box and Urdu).
- Financial Insights — **page redesigned for non-technical users** (same family as the Students and Financial Overview pages): a short *What to do now* note, one *Month* bar with **Previous month / Next month / This month** and a *Show month* button, and a **Back to Financial Overview** button that keeps the same month.
- Financial Insights — **one short answer first**: "3 thing(s) need your attention in October 2026." (amber), "Everything looks fine for October 2026." (green) or "Not enough history yet." (grey) with a plain line saying why. Under it **four big numbers in everyday words**: *Fees paid this month* (with a bar), *Old dues paid this month*, *Salaries vs money received* ("out of every Rs 100 received, about Rs 58 went to salaries") and *Net Position*. Each shows a small coloured tag against last month (*Better than / Lower than / Same as last month*) instead of "percentage points".
- Financial Insights — **"What to do" now has a button for every step**: *See who owes*, *Send reminders*, *Open expenses*, *Open inventory* and *Open Financial Overview* open the right page directly. It comes **before** "What changed since last month", and when nothing needs attention it says so in one green line.
- Financial Insights — the **shop numbers** (*Shop sales, Cost of items sold, Estimated Net Operating Position, Stock bought*) sit in one *Shop and stock* panel that is hidden when the shop module is switched off; the *Spending by type* and *Students who have left* tables are folded under **See more details**.
- Financial Insights — **Urdu**: every new label, sentence (with amounts and percentages kept in reading order) and button is translated.
- Tests — new `tests/test_financial_insights_redesign.py` covers the redesigned Financial Insights (month bar words, back button, no-history message, headline, a button for every step, order of the panels, change tags, everyday wording only, no native dialogs, Urdu).
- Financial Overview — **page redesigned for non-technical users** (same family as the Students page): a short *What to do now* note, one *Month* bar with **Previous month / Next month / This month** and a *Show month* button, and a plain sentence at the top that answers the main question ("In October the school kept Rs 3,000 after paying its bills" or "…paid out Rs 1,600 more than it received", with how many rupees went out for every Rs 100 received).
- Financial Overview — **three big numbers first**: *Cash In*, *Cash Out* and *Net Position* in one band (green / orange / green-or-red) with two bars that compare money received with money paid out. Below them, two clear lists — **Where the money came from** (fees, other income, shop sales) and **Where the money went** (salaries, other expenses, stock bought) — each with a bar for its share and a *Total* line that matches the big number.
- Financial Overview — **"What do CASH and ACCRUAL mean?"** is explained in one plain line (CASH = money that really moved, ACCRUAL = money that is owed but not moved yet) and every card keeps its CASH / ACCRUAL tag.
- Financial Overview — **money still owed** (*Fees Remaining*, *Salary Remaining*) now sits in two warm-coloured cards of its own, with a link to *See who owes*; this month's fees and the salaries show a progress bar (collected / paid).
- Financial Overview — **plain captions under every chart** (for example "Green is money received, orange is money paid out") and Rs amounts in the chart hover.
- Tests — new `tests/test_financial_overview_redesign.py` covers the redesigned Financial Overview (headline sentence for a profit month and an empty month, the big numbers, the lists, the shop panel switching on and off, and the month buttons).
- QR Attendance — **QR Scans tab redesigned for non-technical users** (same family as the Students and Attendance Sheet pages): a short *What to do now* note, one *Class · Date* bar with **Previous day / Next day / Today**, and one summary band with the number of students, a colour bar with big counts of *Arrived · Late · Not arrived · On leave* and the % who came to school.
- QR Attendance — **one clear list instead of three small tables**: every student is one row with photo, roll number, father's name, a coloured status (*Arrived / Late / Not arrived yet / On leave*) and the scan time. Students who have not arrived come first with a red stripe. One-tap chips (*Everyone, Not arrived, Late, Arrived on time, On leave* — each with its count) and an instant search by name, roll number or father's name. Works on a phone as tappable cards.
- QR Attendance — **the page updates itself every 30 seconds without reloading** (a green *Live · updated 09:15:02* line, an *Update by itself* switch that is remembered in this browser, and an *Update now* button). Only the numbers and the list change, so a form you are filling in (for example the auto-absent settings) is never lost.
- QR Attendance — **guard phone set-up as three numbered steps** (*Allow guard phones → Guard account → Connect the phone with a code*) with a tick on each finished step. The box opens by itself while something is missing and folds into one green *Guard phone is ready* line when everything is done.
- QR Attendance — **auto-absent approval is the first thing on the page** when a list is waiting, with big buttons (*Approve & mark absent* / *No, do not mark anyone*), how many students would be marked and their names.
- QR Attendance — **auto-absent settings asked in plain questions** (*At what time? · Should it ask you first? · Safety check · Wait before telling parents*), each with a one-line explanation, folded under a heading that already says whether it is On or Off.
- Attendance — **Student Attendance page redesigned for non-technical users** (same family as the Students page): a short plain-language header, one *Class · Date* bar with **Previous day / Next day / Today** buttons (no more *Load* button — the page opens as soon as you pick a class or a day), and one summary band with the number of students, a colour bar and big live counts of *Present · Absent · Late · Leave* that change while you tap.
- Attendance — **one clear "What to do now" note** ("Tap Absent, Late or Leave for the students who need it, then press Save Attendance") replaces the stack of blue and yellow boxes; on a saved day it says how to correct a mistake with *Unlock*.
- Attendance — **bigger, clearer status buttons**: each student has four large buttons (Present / Absent / Late / Leave) that turn green, red, amber or grey when chosen, and the whole row gets a matching colour stripe so the absent and late students stand out from far away. The student's photo (or initials), roll number and father's name sit in one tidy cell.
- Attendance — **find a student quickly**: a search box above the list finds a student by name, roll number or father's name as you type, with a *Showing 3 of 40 students* counter.
- Attendance — **the Save Attendance bar stays at the bottom of the screen** while you scroll a long class, with a live line *Ready to save: 38 present · 2 absent · 0 late · 0 on leave* so you can check before you save.
- Attendance — **works on a phone**: on small screens every student becomes one tappable card with full-width status buttons and a full-width Save button.
- QR Attendance — **connect the guard's phone by scanning a code, nothing to type**. On the QR Scans tab there are now three clear steps (allow guard phones → pick or create the guard account with one click → *Connect a phone with a code*). In the School Guard app tap *Scan QR to connect* and point it at the code. The old way (typing the address, username and password) is still there, folded away. A code works for 15 minutes; *New code* makes another. Only an administrator sees the code.
- QR Attendance — **the phone finds the school computer again by itself** when the computer's Wi-Fi address changes (no re-typing). The firewall file `tools\allow_guard_phone_firewall.bat` now also opens the small "find the computer" port; run it once again as administrator.
- Guard app (Android, version 1.1.0) — new **"Not connected" screen** when the phone is not on the same Wi-Fi as the computer: a clear message (no Wi-Fi / computer not reachable), automatic retries every few seconds, a *Try again now* button and *Scan QR to reconnect*. A card scanned while disconnected is clearly marked as *not saved*. The app also sends its traffic over Wi-Fi even when the school Wi-Fi has no internet.
- Payroll — **Staff Salaries page redesigned for non-technical users** (same family as the Teachers and Expenses pages): a short header, one *Showing: October 2026* bar with *Previous / month list / Next / This Month* (the month is now picked from a list instead of a typed month box), a clear **Step 1 · Step 2 · Step 3** strip (*Check the amounts → Save the salaries → Pay and mark as paid*) with the *What to do now* sentence under it, and big summary numbers (teachers saved, total salaries, already paid, still to pay) with a **“% paid” progress bar**. Each teacher now has **one card**: name and ID, a coloured status (*Not saved yet / Waiting to be paid / Part paid / Paid*), attendance chips (Present / Absent / Late / Leave), three clearly named boxes (*Monthly salary · Bonus · Deductions*) with *Use suggested* for the deduction, a big **Take-home** amount that updates while typing, what is already paid and still to pay, any arrears, and buttons with words (*Payslip · Void payment · Pay / Pay rest*). A **Cards | List** switch (remembered in this browser) shows the same teachers one per row on a wide screen.
- Payroll — **find a teacher quickly**: instant search by name or ID, and one-tap chips (*Everyone, Not saved, Waiting to be paid, Part paid, Paid* — each with its count) to show only those teachers.
- Payroll — **Save Salaries and Mark All as Paid now sit in a bar that stays at the bottom of the screen**, next to the live take-home total of the ticked teachers, so there is no scrolling to the end of a long list. A teacher who is not saved yet shows *Save the salary first, then you can pay it* instead of a missing button.
- Payroll — **Pay window asks three plain questions**: *How much are you paying now?* (a *Pay the full amount* button; part payments still allowed) · *How did you pay?* (big Cash / Bank / Cheque buttons instead of a drop-down) · *On which day?* (Today / Yesterday buttons).
- Payroll — **Void payment asks for the reason in a proper box** (with quick reasons: *Entered by mistake, Wrong amount, Entered twice*) instead of the small browser pop-up. It still cancels the latest payment of that teacher, keeps it in history and returns the money to *still to pay*.
- Payroll — a friendlier empty page when there are no teachers yet (button *Go to Teachers*), a *Teachers* shortcut in the header, and the finished state now tells you paid salaries also appear in Expenses as *Salaries*.
- Expenses — **page redesigned for non-technical users** (same family as the Teachers page): a short plain-language header, one *Showing: October 2026* bar with *Previous / month list / Next* and a *This Month | All History* switch, big summary numbers (total spent, number of expenses, biggest spending with its share in %, average), and a new **"Where did the money go?"** strip — one coloured bar with a chip per type of expense; tap a chip to see only those expenses. Expenses show as **Cards** (type, date, big amount, note, Cash / Bank / Cheque, bill number, *Copy / Edit / Void* buttons with words; a whole card opens Edit) or as the full **Table**; the choice is remembered in this browser. Search is instant while typing (cards and table together). Export now also offers an **Excel workbook (.xlsx)** next to CSV and PDF; the menu says which month it exports.
- Expenses — **Add / Edit expense asks five plain questions**: *What kind of expense is it? · How much did you pay? (the amount is shown big and with commas while typing) · What was it for? · On which day? (Today / Yesterday buttons) · How did you pay? (three big Cash / Bank / Cheque buttons)*, then an optional bill number. The category now starts empty so a wrong type is never saved by accident, and the reserved *Salaries* type is no longer offered in the list.
- Expenses — **Void asks for the reason in a proper box** (with quick reasons: *Entered by mistake, Wrong amount, Entered twice*) instead of the small browser pop-up; the entry still stays in history and leaves every total.
- Expenses — salary payments made from Payroll now show *From Payroll* (a link to Payroll) instead of Edit / Void buttons that could only answer "change it from Payroll".
- Expenses — friendlier empty pages: a first-time page explains what to do (and offers *Copy from last month* when there is something to copy); a search that finds nothing offers *Search all months*.
- Inventory — **section tabs**: the long Inventory page now shows one part at a time with tabs at the top: *Items & history* (sell, buy, new item, products and recent activity), *Setup* (with its progress), *Canteen*, *Sets*, *Student stock* (with the number waiting) and, when you owe a supplier, *Supplier dues* (with the amount). Every link and redirect that pointed at a part of the page opens the right tab, and the page remembers the last tab you used.
- Inventory — **canteen "totals only" can now be bought on credit (udhaar)**: when you type a canteen purchase total you can also type the supplier and how much you **paid now**. Only the money really paid becomes an expense; the rest is a supplier due that shows in *Supplier dues* (marked *canteen*) and in the total owed on Financial Overview and Expenses. Pay it later with *Pay supplier* or the *Pay* button on that purchase; every payment is an expense on the day it is paid, and an administrator or owner can void a wrong payment (reason required) so the amount is owed again. Leaving *Paid now* empty is paid in full, exactly as before, and older entries are unchanged. The canteen box shows what was bought, what was paid and what is still owed.
- Fees — **Extra Charge (event / trip)**: a new button on the Fees page adds a one-off amount (picnic, trip, annual function) to every active student of the selected class for that month. Parents pay it together with the fee, it shows in the month's due and can be voided from the student's fee history. Charging the same event twice never charges a student twice.
- Fees — the monthly **due override** in Collect Fee now changes only that month. Before, it also replaced the student's monthly fee for every future month; now the student record is touched only when no monthly fee was ever set.
- Documents — **fees for ID cards and certificates**: on the *ID Cards & Certificates* page the administrator sets one fee for the student ID card and one for certificates (most schools charge the same for everyone), each with an optional **duplicate fee** (blank = same as the first fee), and, if wanted, a different fee for one certificate type (Bonafide, Character, Leaving, Merit). Blank or 0 means free. Nothing changes for a school that sets no fee.
- Documents — **receipt made automatically**: once a fee is set, a single student's ID card or certificate is issued from a short *Issue* page that shows the fee and creates a numbered receipt (DOC-0001, DOC-0002 ...) with a School copy and a Parent copy. The money is counted in Other Income (new category *ID Cards*; certificates use *Certificates*), so Financial Overview, the dashboard and the reports include it. It never touches the student's admission-fee balance.
- Documents — **first time charged, duplicate by choice**: printing the same ID card (or the same certificate type) again for the same student is a *duplicate*; the page lists the earlier issues and the administrator picks **Free** or the **duplicate fee**. Refreshing or re-downloading never makes a second record: the receipt page has *Download PDF*, which rebuilds the same document without a new fee.
- Documents — **Recently issued** list on the Documents page (date, student, document, fee, receipt) and **Void** for a wrong issue (reason required): the fee leaves every total and the next print counts as a first issue again.
- Inventory — **setup checklist** at the top of the Inventory page, three steps with a progress bar: (1) add your items, (2) put in the opening stock, (3) choose the Books set and the Uniform set of every class. Each step shows what is done and what is still missing (items with no stock yet, classes with no set) and has a button for it; *Choose items* opens the New set form already filled with the class, the kind and a suggested name. The checklist turns green ("Ready") when all three are done.
- Inventory — **opening stock**: the stock that is already on your shelf is put in with *Add opening stock* (item, quantity, cost of one, date). It sets the stock and the average cost, but nothing is paid today, so it is **not cash out and not a supplier due**, and the Recent purchases list marks it "Opening stock". The cost only decides profit later; a best estimate is fine.
- Inventory — **one uniform for every class**: a Uniform set saved with *All classes / no class* is used by every class that has no uniform set of its own (a class's own set always wins). Books still need a set per class, because books differ by class.
- Inventory — **canteen inside Inventory**: a new Canteen box asks how the school keeps its canteen — *Item by item*, *Totals only* or *No canteen* (the administrator or owner can change it any time; nothing already saved is lost). It shows the month's sales, what was bought, the estimated profit and the value of canteen stock, with previous / next month arrows.
- Inventory — **Canteen, item by item**: canteen items are ordinary products in the category *Canteen* (the category is now in the suggestions), so purchases, sales, stock, low-stock alerts, cost of goods and profit all work exactly like books and uniform. The Canteen box lists those items and their stock.
- Inventory — **Canteen, totals only**: type the total sales or total purchases of a day (or week) with an optional note. A sales total is counted as income (Other Income, category Canteen) and a purchases total as an expense (new category *Canteen Purchases*), so Financial Overview, the dashboard and the reports include them without double counting. The administrator or owner can void a wrong entry with a reason and it leaves every total.
- Other Income — once the canteen is kept in Inventory, a *Canteen* amount can no longer be typed here (it would count the same money twice): the page explains why and a typed attempt is sent to Inventory > Canteen. Canteen entries made in Inventory still show in the list. Schools that choose *No canteen* keep the old way unchanged.
- Inventory — **admission now takes books and uniform out of stock by itself**: when a new student is admitted with books and / or uniform, every item in the class's books set and uniform set (for example English, Maths, Urdu, or Shirt and Tie, times the number of sets) goes down in stock. The price is already part of the admission fee, so it is **not counted as sales income a second time** — only the cost of the items is counted as Cost of Goods Sold. Older students are never touched.
- Inventory — **if stock is short or the class has no set**, the student is still admitted; nothing is half-taken and a message says what was not deducted. The new **Student stock** box on the Inventory page lists these students with an **Issue now** button for when the stock is in.
- Inventory — **change the books / uniform terms later and the stock follows**: fewer uniform sets than before returns the extra sets to stock, more sets takes more out.
- Inventory — **one single item later** (for example only the English book): in *Record sale* pick the student; tick *Already paid in the admission fee* to lower the stock with no new income, or leave it unticked for a normal sale that counts the money and is linked to the student.
- Inventory — **Void a wrong issue** (administrator or owner, reason required): the items go back into stock and their cost is removed from Cost of Goods Sold. Recent sales show the student's name and a *with admission* tag.
- Inventory — **supplier dues (udhaar)**: when you buy stock you now type who you bought from and how much you **paid now**. A bill of Rs 20,000 with Rs 12,000 paid shows **Rs 8,000 still owed** to that supplier (live total, paid and owed while you type). Leaving "Paid now" empty means paid in full, exactly as before.
- Inventory — new **Supplier dues** box at the top of the Inventory page: every supplier you still owe, with open bills, bought, paid and still owed, and a **Pay supplier** button. A payment settles that supplier's oldest bills first; you can also pay one bill from Recent purchases (Pay button). Paying more than what is owed is refused.
- Inventory — Recent purchases now show Bill, Paid and Owed per purchase, and a new list shows the payments made to suppliers after the purchase day. An administrator or owner can void a wrong payment (reason required); the amount becomes owed again.
- Teachers — **staff cards**: the Teachers page now opens as a grid of cards. Each card shows the photo, name, role, qualification, classes and subjects, pay and joining year, with a coloured edge for the role (leadership, senior staff, teachers, admin staff, other). A dot on the photo shows **today's attendance** (present, late, on leave, absent or not marked), taken from staff attendance. Click anywhere on a card to open the teacher's profile; call, ID card, edit and archive (or restore) are on the card. A **Cards / Table** switch, remembered in this browser, brings back the full table with every column, the Columns picker and the exports.
- Teachers — **summary band** above the list: how many teachers are on the list, the mix by role, how many are in school today (with late, leave, absent and not-marked counts, linking to Staff Attendance), and how many classes have a teacher, naming the classes that have none. Class cover counts active teachers only and always looks at the whole school, even when the list is filtered.
- Teachers — instant search now also finds designation, subjects, phone number and CNIC, and works the same in the cards and in the table.
- Admission No — **can no longer be typed or edited by anyone**: on the Add and Edit Student forms the box is always read-only and the server ignores anything posted for it. The number comes only from the pattern in Settings > General (prefix, digits, start) and changes only there, or through the Automatic Admission No switch (ON: new students are numbered by themselves; OFF: new students get no number). A student who has no number gets the next one when saved with the switch ON.
- Admission No — **one-click numbering for students who have none**: Settings > General shows how many students have no Admission No and a button gives all of them the next numbers of the saved pattern (oldest admission first). Numbers already given are never changed; the action is administrator-only, asks for confirmation and is written to the audit log. The same button appears on the Students page for the administrator while any student has no number.
- Admission No — Settings shows a **live preview** of the pattern while you type (for example prefix `FAIZ-{YY}-`, 4 digits, start 1 shows **FAIZ-26-0001**).
- School Assistant — **remembers the last answer**: after "aaj class 5 ki attendance" you can ask just "aur kal?", "class 6 ka?" or "pichle mahine?"; after a student's details, "uska baqaya?" works. If a name matches several students the assistant asks which one, and the chosen name answers the original question (for example the dues). Nothing is stored on the server.
- School Assistant — **"What needs attention?"** ("aaj kya kaam baqi hain?", "alerts"): one to-do list with attendance not yet marked, payroll not generated (late in the month), fees and salary still unpaid, low stock and today's birthdays.
- School Assistant — **who paid today** ("aaj kis kis ne fees di?"): the day's fee payments with student, class, amount and method, and the total; also works for yesterday or one class.
- School Assistant — **low-attendance students** ("kam attendance wale students", also by month or class): students below 75% with their guardian's phone, following the school's attendance policy (Late counted as present or not).
- School Assistant — **class-wise dues** ("class wise fees baqaya"): how many students owe and how much, for every class, biggest first.
- School Assistant — **comparison with last month** ("pichle mahine se muqabla", "expenses compare karo"): fees collected, expenses and net, this month against last month, with the change in %.
- School Assistant — **new admissions** ("is mahine kitne naye admissions hue?"), **birthdays** (today and the next 7 days, students and teachers) and **teacher details** ("Zafar ka phone number", "uski salary?": phone, classes, subjects, joining date; salary only when asked).
- School Assistant — every answer table has a **Copy table** button (paste into Excel or WhatsApp) and phone numbers in the chat are tap-to-call.
- QR Attendance (phase 3) — **auto-absent**: at a cutoff time the school chooses (default 10:00), students who have no attendance record that day are marked Absent. Students already Present, Late, Absent or on Leave are never changed, weekends and holidays are skipped, and the check runs once a day (if School Manager is opened after the cutoff it still runs once). Switch it on and set everything in the new **Auto-absent** box at the bottom of the QR Attendance page (administrators). It is OFF until you turn it on.
- QR Attendance (phase 3) — **two modes**: *Ask me first (approval)* shows the list on the QR Attendance page and nobody is marked until an administrator presses Approve (or Reject); *Fully automatic* marks them straight away. Approving uses the list as it is at that moment, so a student who arrives while the list is waiting is not marked absent.
- QR Attendance (phase 3) — **safety rule**: in fully automatic mode, if fewer than a minimum percentage of students (default 20%) have arrived by the cutoff, for example because the guard phone or Wi-Fi was off, the list waits for approval instead and the page says why.
- QR Attendance (phase 3) — **absent message delay**: the absent WhatsApp message to the guardian is held back for a number of minutes (default 30) so a mistake can be fixed before it goes out. A waiting absent message is cancelled if the student arrives first.
- QR Attendance (phase 3) — **late correction**: if a student marked absent arrives after the absent message was already sent, the guardian gets a short correction message with the arrival time (can be switched off). It replaces the usual late message, so the guardian receives one message, not two.
- QR Attendance (phase 1, server side) — every student ID card now carries a signed, school-wide unique QR code (the old roll-number QR is not unique across classes, so **ID cards must be printed again**). A new **Gate Guard** user role and a guard-app API let the guard's phone sign in, scan a card and see the student's name, class and photo with Present / Late / Already marked / Invalid QR / Unknown student / School closed / On leave. Attendance is saved in the existing attendance records (late time and minutes follow Settings > school start time and grace minutes; one record per student per day; a student already marked Absent who arrives later is changed to Present/Late; Leave is never changed). New page **QR Attendance** (sidebar) shows the day's present, late and absent / not-arrived lists by class. Works on the school Wi-Fi or a hotspot, no internet; turn on "Allow guard phones to connect" on that page (other devices can reach only the guard app), and run tools\allow_guard_phone_firewall.bat once if Windows Firewall blocks the phone. New license switch: feature "QR attendance" and role "Gate Guard" (Premium plan includes it; other plans need it added in the vendor dashboard). Automatic absent comes in phase 3.
- QR Attendance (phase 2) — the Android guard app source is in `android_guard_app/` (Kotlin, CameraX + ML Kit, works offline on the school Wi-Fi). It signs in with a Gate Guard account, scans the ID card QR and shows the student's photo, name, class and a big Present / Late / Already marked / error result with an English and Urdu message, plus today's present / late / not-arrived numbers. Build the APK with Android Studio (steps in `android_guard_app/README_BUILD_APK.txt`).
- Urdu interface (phase 2) — the WhatsApp Center (connection status, QR panel, automation settings, message queue and logs, bridge notices, live status words and test-message replies), Documents (ID cards and certificates) and Analytics & Exports (filters, KPI cards, chart legends and every export card) now show in Urdu when the interface language is Urdu. Names, class names, phone numbers, folder paths and amounts are never changed; wording not translated yet stays English. Add wording in app/services/i18n_ur.py.
- Licensing — **inspection key**: the vendor dashboard (School page > Inspection key) issues a short, view-only key (6, 24, 48 or 72 hours) that sits on top of the school's real license. While it is valid every module and the Audit Log can be opened, nothing can be changed, and an "Inspection mode" banner is shown to everyone signed in. The school pastes it on the License page like a normal key; it ends by itself (or with "End inspection now"), works only on that computer and with that license, and rolling the Windows clock back does not revive it. It never replaces the real license, and an older build refuses it.
- Licensing — **notice and reminders**: a key can carry a short notice from the vendor (for example "Renewal due on 25 Oct"), shown to the administrator at the top of every page and on the License page. Administrators also get a renewal reminder pop-up 30, 14, 7, 3 and 1 day before the license ends (once for each stage).
- School Assistant — now a round button in the bottom corner of every page (administrators); it opens a small chat panel with quick questions and the same answers and history as before. The sidebar entry was removed; the full page still opens from the panel's address (/assistant).
- Login — an English / اردو button on the login and password-recovery pages (shown when the license includes the language switch).
- Admission — books can now be taken in more than one set: the Add Student form and the admission terms have a "Book sets" box (0 = no books); the price per set stays fixed by the class. Receipts, the admission form and the register show quantity x price.
- Admission No — automatic numbering with a switch in Settings > General (Automatic Admission No) and a pattern the school chooses: prefix (e.g. alberoni-26-, or alberoni-{YY}- for the current year), number of digits and start number. ON: new students get alberoni-26-0001, alberoni-26-0002 ... by themselves and the box on Add Student is read-only; OFF: typed by hand as before. Existing numbers are never changed.
- Admission form — download a student's admission form as PDF or Excel from the student's profile page (details, admission fee / books / uniform summary, signature lines).
- Admission — books and uniform per class: set once in Fees > Admission Fee Settings (books price, uniform price per set, default number of sets). The Add Student form fills them from the class; books, sets and price can still be changed for each student.
- Admission — one receipt for everything: admission fee, books and uniform are paid together and printed on a single A4 receipt with an item table (qty, price, amount, paid, balance).
- Admission — part payments: a payment settles admission fee first, then books, then uniform; whatever is left stays pending and is received later from Admission Fees, with a new receipt each time.
- Admission — the student's admission page can change books and uniform (never below what was already received); the register shows a Books + Uniform column and the export adds the same column at the end.
- Students — **new look for the student list**: a clean summary band at the top (students on the list, a Boys / Girls split bar, and how many students have dues with the total due), search and filters in one tidy bar (gender is now a one-tap switch, *Has dues* is a button), and softer rows with the roll number as a badge and amounts as coloured tags. The school's brand colour is used for highlights. Clicking the **Dues** band shows only students with dues (click again to show everyone).
- Students — **click anywhere on a row** to open that student's full report (before, only the name was a link; the name still works and shows an arrow on hover).
- Students — Import Excel, Archive Bin and Promote Students now sit together in one **Manage** menu beside Export Data, so the top of the page is no longer crowded.
- Student report — an **Admission fee** button in the page header (administrator, when the admission fee is in use) takes you to the student's admission fee page.
- Inventory — **sets (bundles)**: a new Sets box on the Inventory page. A set is a list of items bought or sold together, for example "Class 1 Books" = English + Maths + Urdu, or a full uniform = shirt + pant + tie + shoes. Stock is still kept **item by item**, so a set never hides what is really on the shelf.
- Inventory — **buy a whole set in one entry**: press Buy on a set, type the number of sets, the total bill, what you paid now and the supplier. Every item in the set is filled; the bill is shared across the items by their selling value (so each item gets a fair cost), and any unpaid part becomes one supplier due.
- Inventory — **sell a whole set in one click** (Sell on a set): one of each item goes out, the money and profit are booked per item, and a set is never sold half — if one book is short the school is told which one.
- Inventory — items can still be bought and sold **one by one** at any time (for example 10 extra English Class 1 books, or one student taking only one book); a set only shows how many whole sets the stock can make. Sets can be edited or retired later; earlier purchases and sales never change.
- Inventory — purchases that came from a set show a small "Set: ... x N" label in Recent purchases.
- WhatsApp Center — **page redesigned for non-technical users** (same family as Students and Teachers): a plain header, **one big status card** that says in one sentence whether WhatsApp is connected, needs a scan or is not running (green / amber / red), and the *Send Test Message* and *Refresh* buttons right inside it
- WhatsApp Center — **settings in plain words**: one *Send WhatsApp messages automatically* switch, three clear cards for *Ask me first* / *Send right away* / *Send slowly, one by one*, and the message kinds grouped as Attendance, Academic and Finance alerts. Message wording and the Cloud API details are tucked into *Edit message wording* and *Advanced: how WhatsApp connects* so they no longer crowd the page
- WhatsApp Center — **QR connection in three steps**: the QR code sits in its own card with the three things to do on the school phone written next to it
- WhatsApp Center — **Message Queue tells you what to do**: a banner such as *3 message(s) are waiting for your approval* with an **Approve all** button, *N message(s) could not be sent* with **Try all again**, or *Nothing is waiting* when everything is done
- WhatsApp Center — **summary band you can click**: Waiting approval, Approved, Delivered and Failed are one band; clicking a number filters the list. Status and message-type menus filter at once, with a **Clear filters** button
- WhatsApp Center — the queue list now shows **friendly names** (Absent alert, Payment slip, ...) instead of codes like `attendance_absent`, a short preview of each message, and *Tried 2 times* under a status
- WhatsApp Center — **Urdu**: every new label, sentence and button on the page is translated, including the status messages that change while the page is open
- Tests — new `tests/test_automation_page_redesign.py` covers the redesigned page (plain status, mode cards, save settings, Approve all, Try all again, friendly labels, and a guard that the list is not loaded row by row)

### Changed
- Sidebar — **a little lighter and smaller menu text** on a normal screen, so names like *Daily Attendance* and *Classes & Subjects* fit on one line more often; the open page stays bold.
- Sidebar — the **Finance links are written once** and shared by the administrator and the accountant (before, the same block was copied twice), the menu moved into its own file `app/templates/_sidebar_nav.html`, and *Other Income* got its own hand-with-coin icon so it no longer looks like *Fees Management*.
- Class Results — marks are shown without a trailing `.0` (*42* instead of *42.0*), the same on the page and in the tooltip.
- Class Results — the *Report* button on each row is now a small PDF icon button (with a tooltip), so the remarks box and the button fit on screen without sideways scrolling on most monitors.
- Financial Insights — **wording made simpler**: *Collection rate* is now *Fees paid this month*, *Arrears recovery* is *Old dues paid this month*, *Salary burden* is *Salaries vs money received*, *Recommendations* is *What to do*, *What changed* is *What changed since last month*, *Cost of Goods Sold* is *Cost of items sold*. Sentences are shorter, for example "Fee collection is weaker than last month: 51.4% paid now, 71.4% last month.", "You received 108.0% more money than last month (…)" and "Utilities spending went up 300.0% since last month (Rs 1,500.00 more).". The rules stay: Net Position is never called profit, the Estimated Net Operating Position is never called cash, and nothing claims to predict.
- Financial Insights — the page now works out its figures **once** instead of three times, so it opens faster. The figures themselves are unchanged and still match the Financial Overview.
- Tests — `tests/test_phase4_reports.py` updated for the simpler wording (the hand-calculated figures are unchanged).
- Financial Overview — the **Alerts box moved up**, right under the three big numbers, so what needs attention is seen first. The long list of eleven small cards became the three big numbers plus the two lists, the owed cards and the shop panel. Wording is shorter and simpler (one short line under each number), the CASH / ACCRUAL tags stay only on the big numbers and the owed cards, the *Shop and stock* panel shows only when the shop has sales, stock bought or costs, and the comparison tables and date-range compare are folded under **Compare with other months or years** (they open by themselves when you pick a comparison). Every figure, link, export, comparison, chart and alert is still there and calculated exactly as before; only the layout and wording changed.
- Financial Overview — the page header now holds only **Export**; the month buttons moved to their own bar with words instead of arrows. *Show* is now **Show month**.
- Financial Overview — the *Compare periods* buttons are rounded pills with the line "tap one", and the comparison tables, month-by-month tables and Payroll table use the same flat white panels as the rest of the page.
- Attendance — **WhatsApp tools moved into one small *WhatsApp* menu** in the page header (connection status, *Send Absent Alerts*, *Test WhatsApp*) instead of a large technical card above the class list. *Export* (PDF / Excel / CSV) sits next to it. Nothing was removed.
- Attendance — **"All Absent" now asks first** ("Mark every student of this class as Absent?") and sits in the *…* menu, away from *All Present*, so one wrong tap cannot mark the whole class absent. *All Present*, *Reset* and *All Students at Time* work as before.
- Attendance — the **check-in time box** of an Absent or Leave student is hidden (and not sent), and comes back with the time you had typed when you change the student to Present or Late.
- Attendance — a friendlier empty page: *No students found in this class* offers **Go to Students**, and a school with no classes yet is sent to **Go to Classes**.
- Urdu — the new attendance wording (day buttons, search box, save bar, hints, empty pages) is translated.
- Expenses — a **month you picked now stays in force** when you add a search or a type of expense: searching *Electricity* inside October looks only in October (before, it silently switched to all history). A search without a month still looks through all months, and *All History* still shows everything. The *Choose exact dates* boxes are no longer pre-filled with the month's first and last day, so *Apply* cannot turn a month into a date range by itself. The month is now a dropdown list of months instead of a typed month box.
- Expenses — *Copy* / *Continue* from the pick list now keeps the "copied from expense #…" link to the original entry (the Add form used to clear it when it opened).
- Inventory — simpler page for non-technical users: three big buttons at the top (**Sell an item**, **Buy stock**, **New item**) and a *Go to* line that jumps to Setup checklist, Canteen, Sets, Student stock, Supplier dues and the item list. The three forms now sit in tabs (Sell is open first) instead of three narrow columns side by side; the *Add an item* links in the checklist and Canteen box open the *New item* tab. Nothing was removed and no number changed.
- Other Income — redesigned: the month's total and number of entries in large tiles, a small total per category, one clear **Add money received** box ("What is it for?", amount, date, note) and the *new category* form tucked away until needed. The list now also shows the receipt number (for example ADM-0001, DOC-0001).
- Admission Fees — register shows **Total fee, Received and Still to collect** in large tiles, quick **status buttons** (All, Pending, Partial, Paid, Waived) that keep your class, search and date filters, and one tidy table (admission, books + uniform and concession are shown in small text under the total fee). Exports are unchanged.
- Admission Fees — a student's page starts with three big numbers (total, received, still to collect); the administrator's *change fee / concession / books / uniform* form is folded away (it opens by itself when no fee is set yet).
- Documents — printing a **whole class** of ID cards or certificates never charges a fee and keeps no record (it is a school batch print). Only a single student's document is issued with a fee.
- Documents — when a fee is set, a teacher can no longer download a single student's ID card or certificate directly (a message sends them to the school office); the administrator issues it. Staff ID cards are not charged.
- Financial Overview — money paid to suppliers (Cash Out, "Purchases") now counts **when it is really paid**: the part paid on the purchase day in that month, later instalments in the month they are paid. The unpaid part is not cash out yet, and stock is still never an expense. Old purchases count as fully paid, so no past number changes. The month figures also carry the total still owed to suppliers.
- Teachers — page redesigned to match the Student page: the designation, gender and class filters apply as soon as you pick them, Active / Archived / All is a one-click switch, a whole table row opens the profile, the edit / archive / ID card buttons are cleaner icons, and Export, Columns, Manage (Import Excel, Archive Bin) and Add Teacher sit in one toolbar. The table now always opens in name order instead of sorting by the photo column. Urdu wording is added for every new label.
- Add / Edit Student — the Admission No box now shows the number that will be given (in bold, read-only); the Add form showed an empty box before. A student with no number yet shows the next number in the Edit form.
- Students — the **Admission No column is now shown by default** in the student table (it was hidden unless chosen in the column picker; a column choice already saved in a browser is kept), and the search box also finds a student by Admission No.
- School Assistant — the absent / late list now shows the guardian's phone (teacher's contact for staff) so parents can be called straight away. "teacher phone number" without a name now asks "Which teacher?" instead of "Which student?". Existing questions give the same answers as before.
- Automation — a WhatsApp message can now be held until a set time before it is handed to WhatsApp (used by the absent message delay); the Message Queue filter has a new type, *attendance_correction*.
- Admission — a class with only books or uniform (no admission fee) now also switches the admission feature on.
- Automation — the Quick Broadcast tab was removed; the Message Queue & Logs table is now a DataTable (search, sort, page size) and keeps its page, search and sort after Approve / Reject / Retry, until you leave the page.
- Automation — the late-arrival WhatsApp message now includes the arrival time and minutes late (for example "at 8:47 AM (17 minutes late)"); templates saved earlier get the time added automatically.
- Classes — after saving a class, section, subject or fee, the same classes stay open and the page returns to the same scroll position.
- Fees — Billing Month is now a dropdown listing the current month and the months that still have unpaid fees (newest first); "Set Monthly Fee for Entire Class" moved up beside the other header buttons.
- Students — each row now has only **two actions: Edit and Archive / Status Change** (small icon buttons). Student ID Card, Issue Certificate and View Detailed Report were taken off the row: all of them are one click away from the student's report (Documents tab), which opens when you click the name or the row.
- Students — the "What to do now" hint, table header and badges got a lighter style; the table keeps every column, the Columns picker, exports and sorting exactly as before.
- WhatsApp Center — **opens and reloads much faster**: the queue counters now come from one database query instead of six, each row's student is loaded together with the list instead of one query per row, the unused student and class lists are no longer loaded, and the list sends the newest 300 messages (the filters reach older ones)
- WhatsApp Center — **Approve, Reject, Retry and Save no longer run the page queries first**; they act and return straight away
- WhatsApp Center — the page now checks WhatsApp every 12 seconds (every 4 seconds only while a QR code is on screen), only while the Connection tab is open and the browser tab is visible, and never two checks at once. Before, it asked every 3 seconds and kept going in the background, which kept the server busy and made every other page feel slow
- WhatsApp Center — the QR code is requested only when WhatsApp actually asks for a scan
- WhatsApp status check — waits at most about 1.5 seconds for the WhatsApp component (was 3), so the Dashboard and WhatsApp Center no longer hang when the component is stopped
- WhatsApp Center — the information box about the WhatsApp component is shown only when something needs attention (missing, no Node.js or stopped)

### Fixed
- Sidebar — **Other Income, Admission Fees, Inventory & Sales and Financial Insights never lit up** when you were on their page. They now do.
- Sidebar — on the **Financial Overview** page the *Attendance Summary* link also lit up, on the **Financial Insights** page *Financial Overview* lit up too, and on the *Student outstanding* and *Admission fee* pages *Students* lit up. Now only the one correct link is highlighted.
- Sidebar — the finance links were placed inside another menu entry (invalid page markup that could confuse screen readers); every link is now its own entry.
- Class Results — choosing a test type that has no tests (or a class with students but no tests) now shows the friendly *No tests of this type for this class* page with the *Show all test types* button, instead of an empty table of "N/A" rows; the PDF buttons are hidden in that case. A stray English word in the page's style comment no longer stops the Urdu page from being fully translated.
- Teacher Attendance Summary — a wrongly typed or empty date in the address no longer shows an error page; the dates are corrected (or the current month is shown) and the page opens normally.
- Attendance Summary: dates typed the wrong way round (From later than To) are now put the right way round, and a mistyped or broken date in the page address (for example `?start_date=abc`) no longer shows an error page; the page opens on this month instead.
- Teacher Attendance: a mistyped or broken date in the page address (for example `?date=abc`) no longer shows an error page; the page opens on today instead.
- Attendance — **the current time was never filled in automatically** on today's sheet when a student was changed from Absent to Present or Late (the page did not know it was "today"). It now fills the time as intended; past days are still left empty for you to type.
- Expenses — Edit and Void could answer "Salary-generated expenses are managed from Payroll" for **every** expense when the salary link came back as an (empty) list, because an empty list is not `None`. The check now asks whether a salary payment really exists.
- Inventory — the **Student stock box** (students waiting for their books / uniform, the *Issue now* button and the recent issues) was shown only while the school still owed a supplier money. It now always shows.
- Tests — the old check for the removed *Quick Broadcast* builder was contradicting the Phase 1 UI test; it now confirms the builder is gone

### Removed
- Students — the *Download ID card*, *Issue certificate*, *View detailed report* and *Admission fee* icon buttons on each row of the student list (the report page offers all of them: ID card and certificates under Documents, Admission fee in the header).

### Security
- QR Attendance — the guard's phone now keeps a **connection key** instead of the guard's password. The key stops working by itself when the guard account's password is changed or the account is switched off, and the phone then asks to be connected again. Connection codes work for 15 minutes, can only connect *guard* accounts (never an administrator), and wrong attempts are limited like password sign-ins.

## [2.3.0] - 2026-10-16

Subscription licensing — each school's license now says which modules it
includes and how many WhatsApp messages it may send, and a forgotten
administrator login can be recovered safely without internet.

### Added
- Licensing — a license can include or leave out individual modules: Expenses,
  Payroll, Financial overview & insights, Inventory & other income, Admission
  fees, the Principal's dashboard, Attendance, Exams & results, ID cards &
  certificates, Timetable, Parent portal, WhatsApp automation, the School
  Assistant and bulk Import. A module that is not in the plan disappears from
  the menu and shows a "Not included in your plan" page if opened directly.
  Licenses issued before this release keep every module.
- License page — shows the plan, the key revision, which modules are included
  and the WhatsApp usage.
- WhatsApp — daily and monthly sending limits set by the license, to protect the
  school's number from being blocked. Messages over the limit are not lost: they
  stay in the queue and go out automatically the next day or month. The
  Automation page shows how many have been used (for example "Today 37 / 100").
  Test messages count towards the limit too.
- Login — **Forgot username / password?** recovery that works offline. The school
  sends the vendor a request code, the vendor replies with a one-time reset
  token, and the school then picks the administrator account (the username is
  shown) and sets a new password. It also works while the license is expired.
- Licensing — a newer key for the same license replaces an older one; an older
  key can no longer be applied by mistake.
- Vendor tools — a **License Manager dashboard** that runs only on the vendor's
  own laptop: schools, plans, issuing / renewing / updating keys, moving a
  school to a new computer, payments, renewal reminders and password-recovery
  tokens. It is not part of the installer.

### Changed
- Licensing — the command-line tool `tools/license_admin.py` can now set modules,
  plan, revision and WhatsApp limits (`--features`, `--plan`, `--rev`,
  `--wa-daily`, `--wa-monthly`).

### Security
- Recovery — reset tokens are signed by the vendor, work once, only on the school's
  own computer, and expire; wrong tokens are throttled. No password is ever
  revealed or stored by the vendor.
- Vendor tools — the license signing key is kept encrypted on the vendor's laptop,
  and the product build is tested never to include the dashboard or its data.

---

## [2.2.0] - 2026-10-13

### Added
- Admission fee — a one-time fee for new students. Set a school-wide admission fee
  (and, optionally, a different fee per class) from **Fees → Admission Fee Settings**; the
  Add Student form then fills it in automatically and an administrator can edit it, give a
  concession (percentage, fixed amount or full waiver, reason optional) and take the money
  at once. A teacher adding a student records the standard fee as pending. Money is kept
  as numbered receipts (ADM-0001…) that can be printed, voided with a reason, and paid in
  instalments. New **Admission Fees** register and per-student page. The money is stored as
  Other Income, so it shows in Cash In, the dashboard account book and the comparisons, and
  never touches the monthly-fee ledger. Opt-in: nothing changes until a fee is set, students
  admitted earlier are untouched ("not applicable"), and the upgrade takes a safety backup
  of the database before adding its new columns.
- Students — bulk import accepts optional Admission Fee, Admission Concession and
  Admission Fee Paid columns (administrator only, once an admission fee is set). An amount
  already paid is kept as an opening amount that is **not** counted as income, so past
  months never change; the administrator can tick one box to record it as income instead.
  The students list and its PDF/Excel/CSV exports gain Admission Fee, Received, Pending
  and Status columns, and administrators get a one-click link to a student's admission page.
- Admission fee — the register exports to PDF, Excel and CSV (also under Reports → Finance),
  following the page's filters. The Financial Overview and the Principal's dashboard show
  admission fees received on their own line; the amount is already inside Cash In and is
  never added twice.
- Assistant — new **School Assistant** page for administrators. Ask in English or
  Roman Urdu and get answers from your own data: today's attendance, fees collected,
  defaulters, a student's dues, expenses, salary, profit and student/teacher counts,
  plus short how-to guides. Works fully offline with no AI service, and is read-only.

### Fixed
- Backup — the Backup button on an installed product failed with "Database file not
  found: C:\Program Files\School Manager\_internal\instance\school.db". Backups now
  always read the live database from the school's data folder
  (`%LOCALAPPDATA%\SchoolManager`), matching where the app actually stores it.

---

## [2.1.0] - 2026-10-10

Timetables — the timetable system was rebuilt around two templates, and the
old one was removed.

### Added
- Timetables — two ready-made layouts to choose from: **Teacher-wise Chart**
  (teachers down the side, periods across, breaks as grey bands) and **Class
  Weekly Grid** (one grid per class, days across). Both are views over the same
  saved timetable, so switching layout never changes the data.
- Timetables — **one-click Generate** builds a clash-free timetable for the
  ticked classes from your own classes, subjects, teachers and period
  structure. No teacher is ever booked in two places at once.
- Timetables — manual editing: change the subject or the teacher in any cell
  and save; reopening the timetable shows the latest saved version.
- Settings — **Timetable Periods** on the Academic tab: periods per day,
  minutes per period, break position and length, and the break label. The
  Timetables page reads these automatically, so timings are never re-entered.
- Timetables — a Period Settings shortcut on the hub, and the saved timetable
  is remembered per class/section.

### Changed
- Settings — the first period now starts at the **School Start Time** from
  School Settings, so timings have a single source of truth.
- Classes — the per-class "Timetable" link now opens the Timetables page
  instead of a separate per-class editor.

### Removed
- Timetables — the old timetable surfaces are gone: the Master Timetable page
  (period structure, required-periods and the preview-then-apply generator),
  the per-class timetable editor with its PDF export, the conflict auto-fix
  flow, and the date-wise daily substitutions sheet. The hub's one-click
  generation replaces them.
- Timetables — the transient `timetable_drafts` scratch table is dropped on
  upgrade. No timetable data, class, subject, teacher or school setting is
  affected.
- Timetables — teachers keep their own timetable views and conflict
  reporting; only the administrative editors above were removed.

---

## [2.0.0] - 2026-10-09

New modules since 1.0.0 — Other Income, Inventory & Sales, and the
Financial Insights page — plus advance credit and write-off switched on,
the restored period-comparison panel, and a payroll page fix.

### Added

- Insights — a plain-language "Financial Insights" page for the owner: shows how
  much was collected, how much was expected, arrears recovered, salary burden,
  the biggest expense increases and sales performance, each with a short note on
  what needs attention
- Reports — the expenses report can now be downloaded as an Excel (.xlsx) file,
  alongside the existing PDF and CSV
- Fees — the receipt now shows where the money actually went, listing each month
  the payment settled (for example "Rs 1,000 applied to August 2026") instead of
  only the month it was recorded from
- Fees — advance credit and write-off are now switched on: a payment larger than
  the outstanding dues is accepted and the extra is held as credit for the
  student, and an uncollectable balance can be written off with a reason

### Changed

- Financial Overview — the period-comparison panel is back: pick two or more
  months, whole years or sessions and see them side by side, with a difference
  column, a chart and a month-by-month breakdown

### Fixed

- Payroll — the Payroll page no longer shows "500 Unexpected error" once a
  month's payroll has been saved; recording a salary payment works and the
  message it shows quotes the right amounts

---

## [1.0.0] - 2026-10-05

First commercial release of the Windows product
(`SchoolManager_Setup_v1.0.0.exe`), built by the 7-phase product program:
offline licensing → offline assets & launcher → WhatsApp core → code
obfuscation → executable packaging → installer → release QA.

### Added

**Core school modules**

- Students — admissions, profiles with optional photos, custom fields
  (with mandatory-field support), per-class roll numbering with cascade
  shifting, Excel/CSV import with validation, exports, archive/restore,
  per-student change history
- Teachers — records with qualification, experience and salary structure
  (monthly/hourly)
- Classes — classes, sections, subjects, per-class standard fees, editable
  Monday–Saturday timetable with period timings and PDF export
- Attendance — daily student and teacher attendance (Present/Absent/Late/
  Leave) with late check-in times, whole-class quick marking, summaries
  and exports
- Fees — append-only transaction ledger (charges/payments/adjustments),
  explicit monthly charge generation, partial payments, numbered receipts,
  reconciliation with discrepancy repair, defaulter exports, WhatsApp
  reminder queue, class-wide fee updates with confirmation
- Expenses — categories, expense log, one-click "continue last month's
  expense", monthly scoped views and exports
- Tests & exams — class tests, whole-class batch mark entry with proper
  absent handling, configurable grading scale, term exams with date sheets
  and tabulation with positions
- Reports & documents — result cards, transcripts, tabulation sheets, date
  sheets, student/teacher ID cards (photo optional), certificates — as
  print-ready PDFs; Excel/CSV exports across the system
- Payroll — monthly staff payroll with attendance snapshots, deductions
  and payment tracking
- Expenses & financials — income/expense summaries and period comparisons
- Parent portal — read-only access for guardians, limited to their own
  children (multiple children supported)
- Administration — school profile with logo and brand colours, academic
  session, grading scale, holiday ranges, backups (manual + automatic
  hourly with retention), audit trail with CSV export

**WhatsApp automation (core component)**

- Node bridge shipped inside the installer with its own private Node
  runtime; schools never install Node.js
- QR-code pairing with the school's WhatsApp number; the session survives
  updates (stored in the data folder)
- Guardian notifications for absence/late/results with editable templates,
  plus class broadcasts
- Three sending modes: approval, auto, delayed (human-paced)
- Delivery status tracking and logs; message queue with retry counters
- Optional Meta Cloud API integration method
- Robust socket configuration and process-level error guards so transient
  network problems never crash the bridge

**Windows product experience**

- Desktop launcher: one double-click opens a standalone app window
  (Edge/Chrome app mode); `--browser` opens a normal tab
- "Exit Software" button (sidebar, with confirmation dialog) and
  window-close both shut the background server down gracefully
- Per-school data folder (`%LOCALAPPDATA%\SchoolManager`) holding the
  database, license, WhatsApp session, photos, backups and logs — with
  automatic migration from older layouts
- First-run setup wizard with optional demo-data generation (choose
  students/teachers, history period 1 month → 10 years, and which areas to
  include) running in the background with a live progress screen
- Boot diagnostics written to `school_manager.log`
- Automatic hourly database backups with retention

**Licensing (offline)**

- Ed25519-signed license files bound to the Windows machine code
- Expiry warning (last 30 days), grace period (default 7 days), then a
  read-only lockout that always preserves viewing, printing, exports,
  login, backups and license activation
- Signed "latest date seen" state defeating clock rollback; replacement
  keys for wrong far-future clocks
- Vendor-only CLI (`tools/license_admin.py`): key-pair init, license
  issuing with ledger, inspection, machine-code lookup

**Installer & release pipeline**

- Inno Setup installer with Ahmi software firm branding, stable AppId for
  in-place updates, desktop/start-menu shortcuts, clean uninstaller —
  school data preserved on update and uninstall
- PyArmor-obfuscated application code frozen into a windowed
  `SchoolManager.exe` (PyInstaller onedir) with an embedded `--selftest`
  (routes, offline assets, license gate, bundled bridge)
- Vendored UI libraries (Bootstrap, Font Awesome, jQuery, DataTables,
  qrcodejs, Chart.js) for a fully offline interface
- One-command release build (`tools/make_release.py`): clean rebuild, full
  test suite gate, installer compilation, SHA-256 manifest

**Security**

- Five roles (Administrator, Principal/Owner, Accountant, Teacher,
  Parent/Guardian) with deny-by-default per-endpoint authorisation
- Complete audit trail with before/after JSON snapshots and business
  events (logins, charges, payments, voids, settings changes, exports,
  user administration, reminders)
- scrypt password hashing, login throttling with lockout, HttpOnly/
  SameSite session cookies
- Server binds to `127.0.0.1` only; the WhatsApp bridge authenticates with
  a per-launch token

### Changed

- Setup wizard: the "Load demo data" option is **off by default** — schools
  start with a clean database
- Fees page: monthly charges are created via an explicit "Generate monthly
  charges" action (a page load never writes billing data), which also lets
  read-only (expired-license) schools view any month

### Fixed

- Student edit no longer fails for records without a stored sponsor CNIC
- Photo replacement on Windows no longer fails when a browser still holds
  the previous image open
- Report-card PDFs, ID documents and transcripts resolve the school logo
  from the data folder (the install directory is read-only)

---

## Format note

This changelog follows the [Keep a Changelog](https://keepachangelog.com)
structure. See also: `ROADMAP.md` (what comes next),
`docs/RELEASE_CHECKLIST.md` (how to ship), `docs/PRODUCT_OVERVIEW.md`
(what to tell schools).