"""JD instructions prepare only explicit materials, with exact source locators."""

import hashlib


def test_explicit_application_documents_keep_exact_job_source():
    from career_evidence_graph.application_materials import jd_material_requirements

    jd = "Build reliable services. Please submit your CV and a cover letter."
    application = {"id": "synthetic-job", "job_description": jd}
    requirements = jd_material_requirements(application)

    assert [item["kind"] for item in requirements] == ["resume", "cover_letter"]
    assert len({item["id"] for item in requirements}) == 2
    for item in requirements:
        assert item["id"].startswith("jd-")
        assert item["origin"] == "jd"
        assert item["type"] == "file"
        assert item["required"] is True
        assert item["question"] == "Please submit your CV and a cover letter."
        assert item["jd_quote"] == "Please submit your CV and a cover letter."
        assert item["jd_span"] == [25, len(jd)]
        assert item["jd_sha256"] == hashlib.sha256(jd.encode()).hexdigest()
        assert "field_id" not in item and "draft_path" not in item
    assert jd_material_requirements(application) == requirements
    assert (
        jd_material_requirements({**application, "job_description": jd + " New scope."})[0]["id"]
        != requirements[0]["id"]
    )


def test_qualifications_optional_and_negative_text_do_not_create_required_attachments():
    from career_evidence_graph.application_materials import jd_material_requirements

    jd = (
        "Applicants must hold a degree certificate and have Python certification. "
        "Do not submit a cover letter. "
        "Please submit a cover letter only if you wish. "
        "Please submit your CV and an optional cover letter."
    )
    requirements = jd_material_requirements({"id": "synthetic-job", "job_description": jd})

    assert [(item["kind"], item["required"]) for item in requirements] == [("resume", True)]
    assert requirements[0]["jd_quote"] == "Please submit your CV and an optional cover letter."


def test_unrecognized_explicit_attachment_retains_its_own_source_without_poisoning_jd():
    from career_evidence_graph.application_materials import jd_material_requirements

    jd = (
        "Our portfolio contains research papers. "
        "Please attach your security clearance document and resume. "
        "Candidates submit experiments to the research team."
    )
    requirements = jd_material_requirements({"id": "synthetic-job", "job_description": jd})

    assert [item["kind"] for item in requirements] == ["unknown", "resume"]
    assert all(item["required"] for item in requirements)
    assert all(
        item["jd_quote"] == "Please attach your security clearance document and resume."
        for item in requirements
    )
    for item in requirements:
        start, end = item["jd_span"]
        assert jd[start:end] == item["jd_quote"]
    assert (
        jd_material_requirements({"id": "other", "job_description": "Portfolio skills required."})
        == []
    )


def test_french_german_and_chinese_application_instructions_reuse_material_semantics():
    from career_evidence_graph.application_materials import jd_material_requirements

    instructions = [
        ("Veuillez joindre votre CV et une lettre de motivation.", ["resume", "cover_letter"]),
        ("Bitte reichen Sie Ihren Lebenslauf und ein Anschreiben ein.", ["resume", "cover_letter"]),
        ("申请时请上传简历、求职信和学位证。", ["resume", "cover_letter", "diploma"]),
    ]
    for jd, expected in instructions:
        requirements = jd_material_requirements({"id": "synthetic-job", "job_description": jd})
        assert [item["kind"] for item in requirements] == expected
        assert all(item["jd_span"] == [0, len(jd)] for item in requirements)
        assert all(item["type"] == "file" and item["jd_quote"] == jd for item in requirements)


def test_documentary_certificates_and_form_motivation_have_distinct_material_types():
    from career_evidence_graph.application_materials import jd_material_requirements

    jd = (
        "Please upload your degree certificate and professional license. "
        "Please explain your motivation in the application form."
    )
    requirements = jd_material_requirements({"id": "synthetic-job", "job_description": jd})
    assert [(item["kind"], item["type"]) for item in requirements] == [
        ("diploma", "file"),
        ("certificate", "file"),
        ("motivation_text", "textarea"),
    ]
    assert requirements[-1]["question"] == "Please explain your motivation in the application form."


def test_local_optional_or_negative_clause_does_not_hide_required_cv():
    from career_evidence_graph.application_materials import jd_material_requirements

    for jd in [
        "Please submit your CV and do not submit a cover letter.",
        "Please submit your CV and a cover letter is not required.",
        "Veuillez joindre votre CV et une lettre de motivation facultative.",
        "Bitte reichen Sie Ihren Lebenslauf und ein freiwilliges Anschreiben ein.",
        "申请时请上传简历、求职信可选。",
    ]:
        requirements = jd_material_requirements({"id": "synthetic-job", "job_description": jd})
        assert [(item["kind"], item["required"]) for item in requirements] == [("resume", True)]


def test_required_application_document_list_and_must_submit_are_actual_instructions():
    from career_evidence_graph.application_materials import jd_material_requirements

    for jd in [
        "You must submit your CV and a cover letter.",
        "Your application must include your CV and a cover letter.",
        "Required application documents: CV and cover letter.",
        "- Please submit your CV and a cover letter.",
    ]:
        requirements = jd_material_requirements({"id": "synthetic-job", "job_description": jd})
        assert [item["kind"] for item in requirements] == ["resume", "cover_letter"]
        assert all(item["jd_quote"] == jd for item in requirements)


def test_distinct_unknown_documents_have_distinct_stable_local_requirements():
    from career_evidence_graph.application_materials import jd_material_requirements

    jd = "Please attach a security clearance document and a writing sample."
    application = {"id": "synthetic-job", "job_description": jd}
    requirements = jd_material_requirements(application)
    assert [item["kind"] for item in requirements] == ["unknown", "unknown"]
    assert len({item["id"] for item in requirements}) == 2
    assert jd_material_requirements(application) == requirements


def test_explicit_attachment_with_unfamiliar_name_is_not_silently_discarded():
    from career_evidence_graph.application_materials import jd_material_requirements

    jd = "Please attach your publication list."
    requirements = jd_material_requirements({"id": "synthetic-job", "job_description": jd})
    assert [(item["kind"], item["type"], item["required"]) for item in requirements] == [
        ("unknown", "file", True)
    ]
    assert requirements[0]["question"] == jd


def test_conditional_cover_does_not_remove_unconditional_resume_instruction():
    from career_evidence_graph.application_materials import jd_material_requirements

    jd = "Please submit your CV and a cover letter only if you wish."
    requirements = jd_material_requirements({"id": "synthetic-job", "job_description": jd})
    assert [(item["kind"], item["required"]) for item in requirements] == [("resume", True)]
