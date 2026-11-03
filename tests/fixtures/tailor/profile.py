"""An invented candidate for render and claim tests. Phone and email are built at runtime."""
AT = "@"
IDENTITY = {"name": {"full": "Riya Testwal", "preferred": "Riya", "resume": "Riya Testwal"},
            "email": "riya.testwal" + AT + "mail.example.com", "phone": "+91 " + "9" + "0000 11111",
            "links": {"linkedin": "https://www.linkedin.com/in/<you>", "other": []},
            "location": {"city": "Noida", "state": "Uttar Pradesh", "country": "IN"}, "source": "user", "updated": "2026-10-25"}
EMPLOYMENT = [
    {"employer": "Sunfield Cloud", "role": "Senior Software Engineer – Backend", "start": "2023-04", "end": None, "location": "Gurugram", "source": "user"},
    {"employer": "Windline Payments", "role": "Software Engineer 2 – Platform", "start": "2019-07", "end": "2023-03", "location": "Pune", "source": "user"}]
EDUCATION = [{"degree": "B.Tech, Computer Science", "institution": "Example Institute of Technology", "start": "2015-08", "end": "2019-06", "source": "user"}]
FACTS = [
    {"kind": "achievement", "text": "Cut checkout API p99 latency from 820 ms to 310 ms for 1.2 million daily users", "employer": "Sunfield Cloud",
     "metrics": [{"name": "p99 latency", "value": "310", "unit": "ms", "as_said": "310 ms"}], "keywords": ["latency"], "source": "user", "status": "confirmed"},
    {"kind": "achievement", "text": "Automated release checks (CI/CD) for 42 services in GitHub Actions, saving 3 hours a day", "employer": "Sunfield Cloud",
     "keywords": ["CI/CD", "GitHub Actions"], "source": "user", "status": "confirmed"},
    {"kind": "achievement", "text": "Migrated 18 services from VMs onto Kubernetes", "employer": "Windline Payments",
     "keywords": ["Kubernetes", "migration"], "source": "user", "status": "confirmed"},
    {"kind": "skill", "text": "Go and PostgreSQL for backend services", "keywords": ["Go", "PostgreSQL", "backend services"], "source": "user", "status": "confirmed"},
    {"kind": "certification", "text": "AWS Certified Solutions Architect – Associate, 2022", "source": "user", "status": "confirmed"},
    {"kind": "other", "text": "Current CTC 14 LPA", "private": True, "source": "user", "status": "confirmed"},
    {"kind": "achievement", "text": "Rolled out tracing on 30 services", "source": "user"}]   # draft
RESUME = {"job": "j-0001", "version": 1, "format": ["pdf", "docx"], "page_limit": 2,
          "header": {"contacts": ["email", "phone", "city"]},
          "sections": [
            {"heading": "Summary", "paragraphs": [{"text": "Backend engineer who cut checkout API p99 latency to 310 ms for 1.2 million daily users and automated CI/CD for 42 services.", "facts": ["f-0001", "f-0002"]}]},
            {"heading": "Experience", "roles": [
              {"employment_ref": 0, "bullets": [
                {"text": "Cut checkout API p99 latency from 820 ms to 310 ms for 1.2 million daily users.", "facts": ["f-0001"]},
                {"text": "Automated release checks for 42 services in GitHub Actions, saving 3 hours a day.", "facts": ["f-0002"]}]},
              {"employment_ref": 1, "bullets": [{"text": "Migrated 18 services from VMs onto Kubernetes.", "facts": ["f-0003"]}]}]},
            {"heading": "Skills", "lines": [{"label": "Backend", "items": ["Go", "PostgreSQL", "backend services"], "facts": ["f-0004"]}]},
            {"heading": "Education", "from": "education.json"},
            {"heading": "Certifications", "items": [{"text": "AWS Certified Solutions Architect – Associate, 2022", "facts": ["f-0005"]}]}]}
NOTES = """# Application notes

## Why I fit
- Cut checkout API p99 latency from 820 ms to 310 ms <!-- facts: f-0001 -->
- Built CI/CD automation in GitHub Actions for 42 services <!-- facts: f-0002 -->

## Gaps and how to address them
- No Kafka experience: say so, point to the Kubernetes migration instead

## Questions to ask
- How many services does the team own? Is there an on-call rota?

## Pay
- Ask for at least 16.8 LPA
"""
