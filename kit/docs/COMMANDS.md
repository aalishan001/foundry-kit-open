JOB SEARCH COMMANDS                                    (type /help to see this again)

GETTING STARTED
/start               interview that builds your profile: facts, search rules, resume format.
                     Stops and resumes any time. Example: /start
/radar               the companies you follow: who's due, how each is read.
                     /radar add Acme https://careers.acme.example/   /radar drop Acme not hiring
                     /radar new   (companies in the pack you haven't added)
                     /radar recipes   (set up job alerts once, so new roles come to you)

FINDING ROLES
/sweep               ranks what the morning sweep found (careers sites, your Job Alerts label, job
                     sites); runs the sweep first if it didn't happen today. Example: /sweep
/check <jobs>        full fit check: level, pay rule, place, match, odds, gaps. Takes job numbers, links,
                     or a pasted job description. Example: /check j-0004 j-0007
                     Ends with "Shortlist which?"

APPLYING
/tailor <job>        a resume (PDF, Word or both) and application notes for one job, built only from your
                     confirmed facts. Example: /tailor j-0004
                     Files land in Resumes\<Company> - <Role>\
/applied <job>       log an application: date, channel (careers site, referral, recruiter...), which resume.
                     Example: /applied j-0004 today via careers site, sent v2

KEEPING TRACK
/refer               referrals: who you know at each company, the ask message to send (you send it), and
                     what happened. Example: /refer ask c-0002 for j-0004   /refer Priya said yes
/update <news>       record what happened: "Acme called, interview round 1 on Friday", "rejected by Beta",
                     "drop j-0009", a new fact about your work, or a change to your rules
                     ("add Oman after the UAE", "make the threshold 25%").
/today               what needs you today, and the next three things to do. Changes nothing.

PRACTICE
/grill <job>         timed mock interview for that job (45 min by default), scored, no do-overs.
                     Example: /grill j-0004 30
/prep <job>          prep for that job's gaps: a 10-minute primer each, what interviewers expect, 3 likely
                     questions with honest answers from your facts, a quiz, free resources (links checked).
                     Example: /prep j-0004     Files land in data\prep\<job>\

HELP
/help                this sheet

Your rules (set in /start): never a lower role than yours; a same-level move only above your pay-rise threshold
(20% unless you chose another); India first, abroad only in your countries, in your order, and only at an
established company (never a startup); preferred places are a bonus, never a filter. LinkedIn and Naukri are
never read: paste the job text instead.
