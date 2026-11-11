import pytest

from career_evidence_graph.audit.models import (
    ArtifactFact,
    AuditAction,
    AuditQuestion,
    ProbeArea,
    ProbePlan,
    ProjectInterviewPlan,
)
from career_evidence_graph.audit.workflow import begin_inspected_audit


def test_generic_contribution_starts_from_inspected_context_without_a_fixture():
    fact = ArtifactFact(
        evidence_id="evidence-synthetic",
        source_locator="synthetic.md#design",
        statement="A synthetic design decision with retained source context.",
    )
    plan = ProbePlan(
        contribution_id="contrib-synthetic-design",
        areas=(
            ProbeArea(
                area_id="technical-design",
                inspected_fact_ids=(fact.evidence_id,),
                unverified_capability="Explain the design decision",
                demanding_prompt="How did you defend this design choice?",
                intermediate_prompt="Why did you choose this design?",
                simple_prompt="What was your design choice?",
                immediately_higher_capability="Operate the complete system",
                evaluation_criteria={
                    d: ("Explain the design and its limitation.",)
                    for d in ("hard", "intermediate", "simple")
                },
            ),
        ),
        question_layer="project-depth",
    )
    snapshot = begin_inspected_audit(
        contribution_id=plan.contribution_id,
        facts=(fact,),
        plan=plan,
        audit_id="audit-synthetic-design",
    )
    assert snapshot.contribution_id == "contrib-synthetic-design"
    assert snapshot.questions[0].question_layer == "project-depth"
    assert snapshot.questions[0].evaluation_criteria == ("Explain the design and its limitation.",)
    assert snapshot.answers == ()


def project_inputs():
    from career_evidence_graph.interview import (
        ContributionContext,
        InventoryContext,
        InventoryEntry,
        SourceFact,
        SourceReference,
    )

    reference = SourceReference(source_id="source-synthetic", capture_hash="sha256:" + "a" * 64)
    fact = SourceFact(
        evidence_id="evidence-synthetic",
        source_locator="synthetic.md#design",
        statement="Synthetic design context.",
        source=reference,
    )
    area = ProbeArea(
        area_id="technical-design",
        inspected_fact_ids=(fact.evidence_id,),
        unverified_capability="Explain the design",
        demanding_prompt="How can you defend it?",
        intermediate_prompt="Why choose it?",
        simple_prompt="What is the choice?",
        immediately_higher_capability="Own the system",
        evaluation_criteria={
            d: ("Explain a design limitation.",) for d in ("hard", "intermediate", "simple")
        },
    )
    depth = ProbePlan(
        contribution_id="contrib-synthetic-design", areas=(area,), question_layer="project-depth"
    )
    transfer = depth.model_copy(
        update={
            "question_layer": "transfer",
            "areas": (
                area.model_copy(
                    update={
                        "changed_condition": "The workload doubles.",
                        "demanding_prompt": "How would you adapt to the larger workload?",
                        "intermediate_prompt": "What changes under the larger workload?",
                        "simple_prompt": "Which workload assumption changes?",
                    }
                ),
            ),
        }
    )
    plan = ProjectInterviewPlan(
        experience_id="exp-synthetic",
        overview=AuditQuestion(
            id="question-overview",
            reason="Introduce the accepted project context.",
            prompt="How would you introduce the project?",
            area="project-overview",
            question_layer="project-overview",
            inspection_reference=fact.source_locator,
            evaluation_criteria=("Describe the goal and personal role accurately.",),
        ),
        depth_plans=(depth,),
        transfer_plans=(transfer,),
    )
    inventory = InventoryContext(
        accepted_inventory_hash="sha256:" + "b" * 64,
        inventory_revision_hash="sha256:" + "c" * 64,
        entries={"exp-synthetic": InventoryEntry(outcome="confirmed", sources=(reference,))},
    )
    context = ContributionContext(
        contribution_id=depth.contribution_id,
        experience_id=plan.experience_id,
        inventory_revision_hash=inventory.inventory_revision_hash,
        scope="Synthetic design scope",
        facts=(fact,),
    )
    return inventory, context, plan


def test_interview_orders_overview_depth_transfer_and_reuses_the_audit_engine(tmp_path):
    import subprocess

    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    from career_evidence_graph.interview import ProjectInterviewAdapter

    inventory, context, plan = project_inputs()
    adapter = ProjectInterviewAdapter(tmp_path, inventory_loader=lambda: inventory)
    snapshot = adapter.start("interview-synthetic", plan, (context,))
    assert snapshot.active_layer == "project-overview"
    snapshot = adapter.act(
        snapshot.interview_id,
        AuditAction(action="answer", answer="A synthetic project introduction."),
    )
    assert snapshot.active_layer == "project-depth"
    assert snapshot.overview_answers[0].answer == "A synthetic project introduction."
    snapshot = adapter.act(
        snapshot.interview_id,
        AuditAction(action="skip-contribution", answer="Skip this depth review."),
    )
    assert snapshot.active_layer == "transfer"
    snapshot = adapter.act(
        snapshot.interview_id,
        AuditAction(action="skip-contribution", answer="Skip this transfer review."),
    )
    assert snapshot.status == "reviewing"
    assert [a.probe_plan.question_layer for a in snapshot.audits] == ["project-depth", "transfer"]
    assert all(a.status == "reviewing" for a in snapshot.audits)


def test_interview_requires_a_separate_private_git_workspace():
    from pathlib import Path

    import pytest

    from career_evidence_graph.interview import ProjectInterviewAdapter
    from career_evidence_graph.workspace import WorkspaceError

    inventory, _, _ = project_inputs()
    with pytest.raises(WorkspaceError, match="not-separate"):
        ProjectInterviewAdapter(Path(__file__).parents[1], inventory_loader=lambda: inventory)


def test_pause_context_and_stale_inventory_do_not_change_retained_answers(tmp_path):
    import subprocess

    import pytest

    from career_evidence_graph.interview import ProjectInterviewAdapter

    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    inventory, context, plan = project_inputs()
    current = [inventory]
    adapter = ProjectInterviewAdapter(tmp_path, inventory_loader=lambda: current[0])
    initial = adapter.start("interview-resume", plan, (context,))
    recalled = adapter.act(
        initial.interview_id, AuditAction(action="request-context", answer="Explain this label.")
    )
    assert recalled.overview_answers == recalled.overview_decisions == ()
    adapter.act(initial.interview_id, AuditAction(action="pause"))
    with pytest.raises(ValueError, match="not allowed"):
        adapter.act(
            initial.interview_id, AuditAction(action="answer", answer="A premature answer.")
        )
    resumed = adapter.act(initial.interview_id, AuditAction(action="resume"))
    assert resumed.plan == initial.plan
    assert resumed.overview_context_requests == recalled.overview_context_requests
    path = tmp_path / "interviews" / initial.interview_id / "snapshot.json"
    before = path.read_bytes()
    current[0] = inventory.model_copy(update={"accepted_inventory_hash": "sha256:" + "d" * 64})
    with pytest.raises(ValueError, match="stale"):
        adapter.act(
            initial.interview_id, AuditAction(action="answer", answer="An answer on stale inputs.")
        )
    assert path.read_bytes() == before
    assert adapter.queue()[0]["interviews"][0]["stale"] is True


def test_unresolved_identity_and_foreign_source_never_start_an_interview(tmp_path):
    import subprocess

    import pytest

    from career_evidence_graph.interview import (
        InventoryEntry,
        ProjectInterviewAdapter,
        SourceReference,
    )

    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    inventory, context, plan = project_inputs()
    unresolved = inventory.model_copy(
        update={"entries": {"exp-synthetic": InventoryEntry(outcome="unresolved", sources=())}}
    )
    with pytest.raises(ValueError, match="not accepted"):
        ProjectInterviewAdapter(tmp_path, inventory_loader=lambda: unresolved).start(
            "interview-unresolved", plan, (context,)
        )
    foreign = context.facts[0].model_copy(
        update={
            "source": SourceReference(source_id="source-foreign", capture_hash="sha256:" + "e" * 64)
        }
    )
    with pytest.raises(ValueError, match="outside accepted"):
        ProjectInterviewAdapter(tmp_path, inventory_loader=lambda: inventory).start(
            "interview-foreign", plan, (context.model_copy(update={"facts": (foreign,)}),)
        )
    assert not (tmp_path / "interviews").exists()


def test_reviewed_three_layer_journey_keeps_prior_answers_and_separate_conclusions(tmp_path):
    import subprocess

    import pytest

    from career_evidence_graph.audit.models import AuditAnswer, BoundaryDecision
    from career_evidence_graph.interview import ProjectInterviewAdapter

    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    inventory, context, plan = project_inputs()
    prior_question = plan.overview.model_copy(update={"id": "question-prior-responsibility"})
    prior_answer = AuditAnswer(
        question_id=prior_question.id, answer="I designed it; an agent coded."
    )
    context = context.model_copy(
        update={"prior_questions": (prior_question,), "prior_answers": (prior_answer,)}
    )

    class EstablishedPort:
        calls = 0

        def decide_boundary(self, question, answer):
            self.calls += 1
            return BoundaryDecision(
                question_id=question.id,
                answer=answer,
                outcome="established",
                rationale="Synthetic observable design explanation.",
                strongest_capability="Explain a bounded design",
                next_higher_not_established="Own the system",
            )

    port = EstablishedPort()
    adapter = ProjectInterviewAdapter(tmp_path, inventory_loader=lambda: inventory)
    snapshot = adapter.start("interview-reviewed", plan, (context,))
    review = AuditAction(
        action="review-conclusion",
        decision="confirm",
        reviewer_id="synthetic-reviewer",
        reason="Review the retained layer conclusions.",
    )
    snapshot = adapter.act(
        snapshot.interview_id, AuditAction(action="answer", answer="Overview"), decision_port=port
    )
    with pytest.raises(ValueError, match="review each layer"):
        adapter.act(snapshot.interview_id, review)
    for layer in ("project-depth", "transfer"):
        assert snapshot.active_layer == layer
        count = port.calls
        snapshot = adapter.act(
            snapshot.interview_id,
            AuditAction(action="request-context", answer="Explain the label."),
            decision_port=port,
        )
        assert port.calls == count
        for answer in ("A bounded explanation", "I owned it.", "Agent-assisted implementation."):
            snapshot = adapter.act(
                snapshot.interview_id,
                AuditAction(action="answer", answer=answer),
                decision_port=port,
            )
    assert snapshot.status == "reviewing"
    for audit in snapshot.audits:
        for entry in audit.conclusion.entries:
            snapshot = adapter.act(
                snapshot.interview_id,
                AuditAction(
                    action="review-entry",
                    entry_id=entry.id,
                    decision="confirm",
                    reviewer_id="synthetic-reviewer",
                    reason="Review synthetic scope.",
                ),
                audit_id=audit.audit_id,
            )
        snapshot = adapter.act(snapshot.interview_id, review, audit_id=audit.audit_id)
    snapshot = adapter.act(snapshot.interview_id, review)
    assert snapshot.status == "completed"
    assert snapshot.overview_reviewer_id == "synthetic-reviewer"
    assert snapshot.contexts[0].prior_answers == (prior_answer,)
    assert snapshot.contexts[0].prior_questions == (prior_question,)
    assert [a.probe_plan.question_layer for a in snapshot.audits] == ["project-depth", "transfer"]
    assert all(a.conclusion.whole_review == "confirmed" for a in snapshot.audits)
    assert adapter.queue()[0]["reason"] == "reviewed"
    assert not (tmp_path / "assessments").exists()


def test_layers_reuse_attribution_answers_without_reusing_capability(tmp_path):
    import subprocess

    from career_evidence_graph.audit.models import BoundaryDecision
    from career_evidence_graph.interview import ProjectInterviewAdapter

    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    inventory, context, plan = project_inputs()
    adapter = ProjectInterviewAdapter(tmp_path, inventory_loader=lambda: inventory)
    snapshot = adapter.start("interview-attribution-recall", plan, (context,))

    class EstablishedPort:
        def decide_boundary(self, question, answer):
            return BoundaryDecision(
                question_id=question.id,
                answer=answer,
                outcome="established",
                rationale="Synthetic explanation, evaluated separately in this layer.",
                strongest_capability=answer,
                next_higher_not_established="Own the system",
            )

    port = EstablishedPort()
    for answer in ("Overview", "Depth design", "I owned it.", "Codex assisted testing."):
        snapshot = adapter.act(
            snapshot.interview_id,
            AuditAction(action="answer", answer=answer),
            decision_port=port,
        )
    assert snapshot.active_layer == "transfer"
    depth, transfer = snapshot.audits
    assert transfer.coverage[0].status == "pending"
    assert transfer.coverage[0].strongest_capability is None
    assert transfer.decisions == ()
    retained = [q for q in transfer.questions if q.turn != "capability"]
    assert [q.turn for q in retained] == ["ownership", "assistance"]
    assert all(q.status == "answered" for q in retained)
    assert all(depth.audit_id in q.reason for q in retained)
    assert {q.inspection_reference for q in retained} == {context.facts[0].source_locator}
    assert [a.answer for a in transfer.answers] == ["I owned it.", "Codex assisted testing."]
    snapshot = adapter.act(
        snapshot.interview_id,
        AuditAction(action="answer", answer="Transfer adaptation"),
        decision_port=port,
    )
    assert snapshot.status == "reviewing"
    assert [a.conclusion.entries[0].strongest_capability for a in snapshot.audits] == [
        "Depth design",
        "Transfer adaptation",
    ]
    assert snapshot.audits[1].attribution_records[0] == depth.attribution_records[0]
    assert adapter.read(snapshot.interview_id) == snapshot


class EstablishedInterviewPort:
    def decide_boundary(self, question, answer):
        from career_evidence_graph.audit.models import BoundaryDecision

        return BoundaryDecision(
            question_id=question.id,
            answer=answer,
            outcome="established",
            rationale="Synthetic explanation for this exact layer.",
            strongest_capability=answer,
            next_higher_not_established="Own the system",
        )


def _context_with_attribution(context, plan, ownership="I owned it.", assistance="No assistance."):
    from career_evidence_graph.audit.models import AuditAnswer

    questions = tuple(
        plan.overview.model_copy(
            update={
                "id": f"question-prior-{turn}",
                "area": "technical-design",
                "capability_area_id": "technical-design",
                "turn": turn,
                "status": "answered",
            }
        )
        for turn in ("ownership", "assistance")
    )
    answers = tuple(
        AuditAnswer(question_id=q.id, answer=text)
        for q, text in zip(questions, (ownership, assistance), strict=True)
    )
    return context.model_copy(update={"prior_questions": questions, "prior_answers": answers})


def test_context_attribution_is_recalled_in_depth_and_transfer_with_original_sources(tmp_path):
    import subprocess

    from career_evidence_graph.interview import ProjectInterviewAdapter

    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    inventory, context, plan = project_inputs()
    context = _context_with_attribution(context, plan, assistance="Codex assisted testing.")
    adapter = ProjectInterviewAdapter(tmp_path, inventory_loader=lambda: inventory)
    snapshot = adapter.start("interview-prior-attribution", plan, (context,))
    for answer in ("Overview", "Depth explanation", "Transfer reasoning"):
        snapshot = adapter.act(
            snapshot.interview_id,
            AuditAction(action="answer", answer=answer),
            decision_port=EstablishedInterviewPort(),
        )
    assert snapshot.status == "reviewing"
    for audit in snapshot.audits:
        assert len([q for q in audit.questions if q.turn == "capability"]) == 1
        assert [a.answer for a in audit.answers[:2]] == [a.answer for a in context.prior_answers]
        assert "I owned it." in audit.questions[-1].recall_reminder
        assert "Codex assisted testing." in audit.questions[-1].recall_reminder
        assert set(audit.conclusion.entries[0].answer_references) == {
            f"answer:{q.id}" for q in audit.questions
        }
    assert snapshot.contexts[0].prior_questions == context.prior_questions
    assert snapshot.contexts[0].prior_answers == context.prior_answers
    assert adapter.read(snapshot.interview_id) == snapshot


@pytest.mark.parametrize(
    "change",
    [
        "ownership",
        "other-person",
        "assistance",
        "mixed",
        "source",
        "missing",
        "skipped",
        "unanswered",
        "duplicate",
    ],
)
def test_uncertain_or_unbound_prior_attribution_must_be_asked_again(tmp_path, change):
    import subprocess

    from career_evidence_graph.interview import ProjectInterviewAdapter

    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    inventory, context, plan = project_inputs()
    context = _context_with_attribution(
        context,
        plan,
        ownership=(
            "I am not sure."
            if change == "ownership"
            else "Someone else owned it, not me."
            if change == "other-person"
            else "I owned it."
        ),
        assistance=(
            "I am not sure."
            if change == "assistance"
            else "No assistance, but Codex assisted testing."
            if change == "mixed"
            else "No assistance."
        ),
    )
    questions, answers = list(context.prior_questions), list(context.prior_answers)
    if change == "source":
        questions[0] = questions[0].model_copy(update={"inspection_reference": "other.md#design"})
    elif change == "missing":
        answers.pop()
    elif change == "skipped":
        answers[1] = answers[1].model_copy(update={"skipped": True})
    elif change == "unanswered":
        questions[1] = questions[1].model_copy(update={"status": "unanswered"})
    elif change == "duplicate":
        answers.append(answers[1])
    context = context.model_copy(
        update={"prior_questions": tuple(questions), "prior_answers": tuple(answers)}
    )
    adapter = ProjectInterviewAdapter(tmp_path, inventory_loader=lambda: inventory)
    snapshot = adapter.start("interview-uncertain-prior", plan, (context,))
    for answer in ("Overview", "Depth explanation"):
        snapshot = adapter.act(
            snapshot.interview_id,
            AuditAction(action="answer", answer=answer),
            decision_port=EstablishedInterviewPort(),
        )
    audit = snapshot.audits[0]
    assert audit.questions[-1].turn == "ownership"
    assert audit.attribution_records == ()
    assert [a.answer for a in audit.answers] == ["Depth explanation"]


@pytest.mark.parametrize(
    "ownership,assistance",
    [
        ("I am not sure.", "No assistance."),
        ("I owned it.", "I am not sure."),
        ("Someone else owned it, not me.", "No assistance."),
    ],
)
def test_unresolved_or_conflicted_depth_attribution_is_not_confirmed_for_transfer(
    tmp_path, ownership, assistance
):
    import subprocess

    from career_evidence_graph.interview import ProjectInterviewAdapter

    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    inventory, context, plan = project_inputs()
    adapter = ProjectInterviewAdapter(tmp_path, inventory_loader=lambda: inventory)
    snapshot = adapter.start("interview-unresolved-layer", plan, (context,))
    for answer in ("Overview", "Depth explanation", ownership, assistance, "Transfer explanation"):
        snapshot = adapter.act(
            snapshot.interview_id,
            AuditAction(action="answer", answer=answer),
            decision_port=EstablishedInterviewPort(),
        )
    assert snapshot.active_layer == "transfer"
    assert snapshot.audits[1].questions[-1].turn == "ownership"
    assert snapshot.audits[1].attribution_records == ()


def test_attribution_from_another_contribution_is_not_reused(tmp_path):
    import subprocess

    from career_evidence_graph.interview import ProjectInterviewAdapter

    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    inventory, context, plan = project_inputs()
    other = context.model_copy(update={"contribution_id": "contrib-other-design"})
    other_depth = plan.depth_plans[0].model_copy(update={"contribution_id": other.contribution_id})
    other_transfer = plan.transfer_plans[0].model_copy(
        update={"contribution_id": other.contribution_id}
    )
    plan = plan.model_copy(
        update={
            "depth_plans": (*plan.depth_plans, other_depth),
            "transfer_plans": (*plan.transfer_plans, other_transfer),
        }
    )
    adapter = ProjectInterviewAdapter(tmp_path, inventory_loader=lambda: inventory)
    snapshot = adapter.start("interview-distinct-contributions", plan, (context, other))
    for answer in (
        "Overview",
        "First explanation",
        "I owned it.",
        "Codex assisted testing.",
        "Second explanation",
    ):
        snapshot = adapter.act(
            snapshot.interview_id,
            AuditAction(action="answer", answer=answer),
            decision_port=EstablishedInterviewPort(),
        )
    assert snapshot.audits[1].contribution_id == other.contribution_id
    assert snapshot.audits[1].questions[-1].turn == "ownership"
    assert snapshot.audits[1].attribution_records == ()


def test_later_denial_of_recalled_assistance_preserves_the_conflict(tmp_path):
    import subprocess

    from career_evidence_graph.audit.models import BoundaryDecision
    from career_evidence_graph.interview import ProjectInterviewAdapter

    class CorrectionPort(EstablishedInterviewPort):
        def decide_boundary(self, question, answer):
            if "did not receive" in answer:
                return BoundaryDecision(
                    question_id=question.id,
                    answer=answer,
                    outcome="attribution-signal",
                    rationale="User corrects the earlier assistance claim.",
                )
            return super().decide_boundary(question, answer)

    subprocess.run(["git", "init", "--quiet", str(tmp_path)], check=True)
    inventory, context, plan = project_inputs()
    context = _context_with_attribution(context, plan, assistance="Codex assisted testing.")
    adapter = ProjectInterviewAdapter(tmp_path, inventory_loader=lambda: inventory)
    snapshot = adapter.start("interview-correct-recalled-assistance", plan, (context,))
    denial = "I did not receive any assistance from Codex."
    for answer in ("Overview", "Depth explanation", denial, "Transfer explanation"):
        snapshot = adapter.act(
            snapshot.interview_id,
            AuditAction(action="answer", answer=answer),
            decision_port=CorrectionPort(),
        )
    transfer = snapshot.audits[1]
    assert transfer.attribution_records[0].ownership == "user-owned"
    assert transfer.attribution_records[0].assistance == "unresolved"
    assert transfer.attribution_records[0].assistance_answer == denial
    assert transfer.attribution_conflicts[-1].user_claim == denial
    assert transfer.conclusion.entries[0].conflicts
    assert any(a.answer == "Codex assisted testing." for a in transfer.answers)
    assert any(a.answer == denial for a in transfer.answers)
    assert adapter.read(snapshot.interview_id) == snapshot
