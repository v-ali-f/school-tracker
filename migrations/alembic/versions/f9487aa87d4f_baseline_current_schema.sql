--
-- PostgreSQL database dump
--


-- Dumped from database version 16.13 (Homebrew)
-- Dumped by pg_dump version 16.13 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: academic_year; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.academic_year (
    id integer NOT NULL,
    name character varying(20) NOT NULL,
    is_current boolean NOT NULL,
    start_date date,
    end_date date,
    is_closed boolean NOT NULL,
    is_archived boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: academic_year_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.academic_year_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: academic_year_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.academic_year_id_seq OWNED BY public.academic_year.id;



--
-- Name: appeal; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.appeal (
    id integer NOT NULL,
    number character varying(80),
    received_at date,
    applicant_name character varying(255) NOT NULL,
    applicant_contact character varying(255),
    channel character varying(80),
    subject character varying(255) NOT NULL,
    description text,
    responsible_user_id integer,
    responsible_user_ids text,
    creator_user_id integer,
    linked_task_id integer,
    deadline_at date,
    status character varying(40) NOT NULL,
    result_text text,
    answered_at date,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: appeal_attachment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.appeal_attachment (
    id integer NOT NULL,
    appeal_id integer NOT NULL,
    original_filename character varying(255) NOT NULL,
    stored_path character varying(500) NOT NULL,
    uploaded_by_user_id integer,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: appeal_attachment_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.appeal_attachment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: appeal_attachment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.appeal_attachment_id_seq OWNED BY public.appeal_attachment.id;


--
-- Name: appeal_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.appeal_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: appeal_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.appeal_id_seq OWNED BY public.appeal.id;


--
-- Name: attendance_import_session; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.attendance_import_session (
    id integer NOT NULL,
    filename character varying(255) NOT NULL,
    imported_by integer,
    created_at timestamp without time zone NOT NULL,
    imported_at timestamp without time zone NOT NULL,
    period_month character varying(7),
    period_year integer,
    period_num integer,
    building_id integer,
    rows_total integer NOT NULL,
    rows_processed integer NOT NULL,
    rows_matched integer NOT NULL,
    rows_unmatched integer NOT NULL,
    rows_late integer NOT NULL,
    rows_early_leave integer NOT NULL,
    rows_absent integer NOT NULL,
    rows_no_entry integer NOT NULL,
    rows_no_exit integer NOT NULL,
    unique_classes integer NOT NULL,
    unique_children integer NOT NULL,
    school_days_count integer,
    notes text
);


--
-- Name: attendance_import_session_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.attendance_import_session_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: attendance_import_session_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.attendance_import_session_id_seq OWNED BY public.attendance_import_session.id;


--
-- Name: attendance_late; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.attendance_late (
    id integer NOT NULL,
    child_id integer NOT NULL,
    class_id integer,
    late_date date NOT NULL,
    late_time time without time zone,
    norm_time time without time zone,
    late_minutes integer,
    source character varying(30) NOT NULL,
    import_session_id integer,
    created_by integer,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: attendance_late_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.attendance_late_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: attendance_late_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.attendance_late_id_seq OWNED BY public.attendance_late.id;


--
-- Name: attendance_pass; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.attendance_pass (
    id integer NOT NULL,
    child_id integer NOT NULL,
    class_id integer,
    pass_date date NOT NULL,
    pass_time time without time zone,
    reason character varying(500),
    issued_by integer,
    status character varying(30) NOT NULL,
    used_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: attendance_pass_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.attendance_pass_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: attendance_pass_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.attendance_pass_id_seq OWNED BY public.attendance_pass.id;


--
-- Name: attendance_raw_entry; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.attendance_raw_entry (
    id integer NOT NULL,
    import_session_id integer NOT NULL,
    child_id integer,
    full_name character varying(255),
    source_class_name character varying(120),
    entry_date date,
    first_in time without time zone,
    last_out time without time zone,
    presence_minutes integer,
    presence_text character varying(120),
    inputs_outputs character varying(255),
    is_late boolean NOT NULL,
    is_absent boolean NOT NULL,
    is_early_leave boolean NOT NULL,
    no_entry_fix boolean NOT NULL,
    no_exit_fix boolean NOT NULL,
    matched_class_id integer,
    raw_payload text,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: attendance_raw_entry_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.attendance_raw_entry_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: attendance_raw_entry_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.attendance_raw_entry_id_seq OWNED BY public.attendance_raw_entry.id;


--
-- Name: attendance_schedule_rule; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.attendance_schedule_rule (
    id integer NOT NULL,
    academic_year_id integer,
    school_class_id integer,
    grade_from integer,
    grade_to integer,
    grade integer,
    start_time time without time zone NOT NULL,
    title character varying(120) NOT NULL,
    comment character varying(255),
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: attendance_schedule_rule_class; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.attendance_schedule_rule_class (
    id integer NOT NULL,
    rule_id integer NOT NULL,
    class_id integer NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: attendance_schedule_rule_class_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.attendance_schedule_rule_class_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: attendance_schedule_rule_class_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.attendance_schedule_rule_class_id_seq OWNED BY public.attendance_schedule_rule_class.id;


--
-- Name: attendance_schedule_rule_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.attendance_schedule_rule_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: attendance_schedule_rule_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.attendance_schedule_rule_id_seq OWNED BY public.attendance_schedule_rule.id;


--
-- Name: attendance_school_day; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.attendance_school_day (
    id integer NOT NULL,
    day_date date NOT NULL,
    month_key character varying(7) NOT NULL,
    is_school_day boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: attendance_school_day_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.attendance_school_day_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: attendance_school_day_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.attendance_school_day_id_seq OWNED BY public.attendance_school_day.id;


--
-- Name: buildings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.buildings (
    id integer NOT NULL,
    name character varying(120) NOT NULL,
    short_name character varying(50),
    address character varying(255),
    created_at timestamp without time zone NOT NULL
);


--
-- Name: buildings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.buildings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: buildings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.buildings_id_seq OWNED BY public.buildings.id;


--
-- Name: child; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.child (
    id integer NOT NULL,
    last_name character varying(120) NOT NULL,
    first_name character varying(120) NOT NULL,
    middle_name character varying(120),
    birth_date date,
    gender character varying(10),
    phone character varying(50),
    email character varying(120),
    education_form character varying(50),
    reg_address character varying(255),
    temporary_address character varying(255),
    actual_address character varying(255),
    notes text,
    created_at timestamp without time zone NOT NULL,
    status character varying(30) NOT NULL,
    archived_at timestamp without time zone,
    is_ovz boolean NOT NULL,
    is_vshu boolean NOT NULL,
    is_low boolean NOT NULL,
    is_az boolean NOT NULL,
    is_disabled boolean NOT NULL,
    ovz_level character varying(10),
    ovz_nosology character varying(20),
    ovz_variant integer,
    ovz_doc_number character varying(100),
    ovz_doc_date date,
    low_subjects character varying(255),
    low_notes text,
    disability_mse character varying(255),
    disability_from date,
    disability_to date,
    disability_ipra character varying(255)
);


--
-- Name: child_comments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.child_comments (
    id integer NOT NULL,
    child_id integer NOT NULL,
    author_id integer NOT NULL,
    text text NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: child_comments_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.child_comments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: child_comments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.child_comments_id_seq OWNED BY public.child_comments.id;


--
-- Name: child_enrollment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.child_enrollment (
    id integer NOT NULL,
    child_id integer NOT NULL,
    academic_year_id integer NOT NULL,
    school_class_id integer,
    status character varying(30) NOT NULL,
    enrolled_at timestamp without time zone NOT NULL,
    ended_at timestamp without time zone,
    note character varying(255),
    transfer_order_number character varying(100),
    transfer_order_date date
);


--
-- Name: child_enrollment_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.child_enrollment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: child_enrollment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.child_enrollment_id_seq OWNED BY public.child_enrollment.id;


--
-- Name: child_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.child_events (
    id integer NOT NULL,
    child_id integer NOT NULL,
    author_id integer NOT NULL,
    event_type character varying(30) NOT NULL,
    from_class character varying(200),
    to_class character varying(200),
    promotion_kind character varying(30) NOT NULL,
    reason character varying(500),
    created_at timestamp without time zone NOT NULL
);


--
-- Name: child_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.child_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: child_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.child_events_id_seq OWNED BY public.child_events.id;


--
-- Name: child_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.child_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: child_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.child_id_seq OWNED BY public.child.id;


--
-- Name: child_movement; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.child_movement (
    id integer NOT NULL,
    child_id integer NOT NULL,
    academic_year_id integer,
    movement_type character varying(30) NOT NULL,
    movement_date date NOT NULL,
    from_class_id integer,
    to_class_id integer,
    reason text,
    order_number character varying(100),
    created_by integer,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: child_movement_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.child_movement_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: child_movement_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.child_movement_id_seq OWNED BY public.child_movement.id;


--
-- Name: child_parent; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.child_parent (
    id integer NOT NULL,
    child_id integer NOT NULL,
    parent_id integer NOT NULL,
    relation_type character varying(30) NOT NULL,
    is_legal_representative boolean NOT NULL,
    note character varying(255),
    transfer_order_number character varying(100),
    transfer_order_date date
);


--
-- Name: child_parent_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.child_parent_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: child_parent_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.child_parent_id_seq OWNED BY public.child_parent.id;


--
-- Name: child_social; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.child_social (
    id integer NOT NULL,
    child_id integer NOT NULL,
    family_status character varying(100),
    living_conditions character varying(255),
    social_risk character varying(255),
    has_disability_parents boolean NOT NULL,
    has_large_family boolean NOT NULL,
    has_low_income_family boolean NOT NULL,
    has_guardianship boolean NOT NULL,
    has_orphan_status boolean NOT NULL,
    has_refugee_status boolean NOT NULL,
    vshu_since date,
    vshu_reason text,
    kdn_since date,
    kdn_reason text,
    pdn_since date,
    pdn_reason text,
    vshu_removed_at date,
    vshu_remove_reason text,
    aoop_variant_text character varying(255),
    is_socially_dangerous boolean NOT NULL,
    is_hard_life boolean NOT NULL,
    is_single_mother boolean NOT NULL,
    is_single_father boolean NOT NULL,
    is_repeat_year boolean NOT NULL,
    is_svo_family boolean NOT NULL,
    notes text,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: child_social_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.child_social_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: child_social_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.child_social_id_seq OWNED BY public.child_social.id;


--
-- Name: child_transfer_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.child_transfer_history (
    id integer NOT NULL,
    child_id integer NOT NULL,
    from_academic_year_id integer,
    to_academic_year_id integer,
    from_class_id integer,
    to_class_id integer,
    transfer_type character varying(30) NOT NULL,
    transfer_date date,
    order_number character varying(100),
    order_date date,
    comment text,
    created_by integer,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: child_transfer_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.child_transfer_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: child_transfer_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.child_transfer_history_id_seq OWNED BY public.child_transfer_history.id;


--
-- Name: class_rating_snapshot; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.class_rating_snapshot (
    id integer NOT NULL,
    class_name character varying(32) NOT NULL,
    year_label character varying(16) NOT NULL,
    place integer,
    total_classes integer,
    total_points double precision NOT NULL,
    activities_json text,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: class_rating_snapshot_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.class_rating_snapshot_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: class_rating_snapshot_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.class_rating_snapshot_id_seq OWNED BY public.class_rating_snapshot.id;


--
-- Name: control_work; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.control_work (
    id integer NOT NULL,
    subject_id integer NOT NULL,
    work_kind character varying(50) DEFAULT 'control'::character varying NOT NULL,
    theme character varying(255) NOT NULL,
    work_date date,
    deadline_date date,
    created_by integer,
    academic_year_id integer,
    grade5_percent integer NOT NULL,
    grade4_percent integer NOT NULL,
    grade3_percent integer NOT NULL,
    retention_until date,
    dictation_grade5_spelling_max integer DEFAULT 0 NOT NULL,
    dictation_grade5_punctuation_max integer DEFAULT 0 NOT NULL,
    dictation_grade4_spelling_max integer DEFAULT 2 NOT NULL,
    dictation_grade4_punctuation_max integer DEFAULT 2 NOT NULL,
    dictation_grade3_spelling_max integer DEFAULT 4 NOT NULL,
    dictation_grade3_punctuation_max integer DEFAULT 4 NOT NULL,
    dictation_use_grammar_errors boolean DEFAULT false NOT NULL,
    dictation_use_corrections boolean DEFAULT false NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by integer,
    manual_status character varying(30),
    is_archived boolean DEFAULT false NOT NULL
);


--
-- Name: control_work_assignment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.control_work_assignment (
    id integer NOT NULL,
    control_work_id integer NOT NULL,
    school_class_id integer NOT NULL,
    teacher_id integer,
    status character varying(30) NOT NULL
);


--
-- Name: control_work_assignment_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.control_work_assignment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: control_work_assignment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.control_work_assignment_id_seq OWNED BY public.control_work_assignment.id;


--
-- Name: control_work_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.control_work_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: control_work_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.control_work_id_seq OWNED BY public.control_work.id;


--
-- Name: control_work_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.control_work_log (
    id integer NOT NULL,
    control_work_id integer NOT NULL,
    user_id integer,
    event_type character varying(50) NOT NULL,
    title character varying(255) NOT NULL,
    old_value text,
    new_value text,
    details text,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: control_work_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.control_work_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: control_work_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.control_work_log_id_seq OWNED BY public.control_work_log.id;


--
-- Name: control_work_result; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.control_work_result (
    id integer NOT NULL,
    control_work_id integer NOT NULL,
    assignment_id integer NOT NULL,
    school_class_id integer NOT NULL,
    academic_year_id integer,
    child_id integer NOT NULL,
    total_score integer,
    percent double precision,
    mark integer,
    result_status character varying(20) DEFAULT 'present'::character varying NOT NULL,
    is_absent boolean DEFAULT false NOT NULL,
    dictation_mark integer,
    grammar_mark integer,
    final_mark integer,
    spelling_errors integer,
    punctuation_errors integer,
    grammar_errors integer,
    corrections_count integer,
    teacher_comment text,
    created_by integer,
    grade5_percent integer NOT NULL,
    grade4_percent integer NOT NULL,
    grade3_percent integer NOT NULL,
    retention_until date,
    is_archived boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: control_work_result_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.control_work_result_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: control_work_result_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.control_work_result_id_seq OWNED BY public.control_work_result.id;


--
-- Name: control_work_task; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.control_work_task (
    id integer NOT NULL,
    control_work_id integer NOT NULL,
    task_number integer NOT NULL,
    max_score integer NOT NULL,
    description character varying(255),
    topic character varying(255)
);


--
-- Name: control_work_task_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.control_work_task_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: control_work_task_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.control_work_task_id_seq OWNED BY public.control_work_task.id;


--
-- Name: dashboard_block_catalog; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.dashboard_block_catalog (
    id integer NOT NULL,
    block_code character varying(100) NOT NULL,
    title character varying(255) NOT NULL,
    category character varying(50) NOT NULL,
    description text,
    default_order integer NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: dashboard_block_catalog_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.dashboard_block_catalog_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: dashboard_block_catalog_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.dashboard_block_catalog_id_seq OWNED BY public.dashboard_block_catalog.id;


--
-- Name: debt; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.debt (
    id integer NOT NULL,
    child_id integer NOT NULL,
    subject_id integer NOT NULL,
    detected_date date NOT NULL,
    due_date date,
    status character varying(20) NOT NULL,
    created_at timestamp without time zone NOT NULL,
    closed_at timestamp without time zone,
    closed_by_user_id integer
);


--
-- Name: debt_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.debt_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: debt_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.debt_id_seq OWNED BY public.debt.id;


--
-- Name: department; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.department (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    code character varying(80),
    description text,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: department_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.department_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: department_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.department_id_seq OWNED BY public.department.id;


--
-- Name: department_leader; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.department_leader (
    id integer NOT NULL,
    department_id integer NOT NULL,
    user_id integer NOT NULL,
    building_id integer,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: department_leader_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.department_leader_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: department_leader_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.department_leader_id_seq OWNED BY public.department_leader.id;


--
-- Name: department_subject; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.department_subject (
    id integer NOT NULL,
    department_id integer NOT NULL,
    subject_id integer NOT NULL,
    academic_year_id integer
);


--
-- Name: department_subject_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.department_subject_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: department_subject_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.department_subject_id_seq OWNED BY public.department_subject.id;


--
-- Name: diagnostic_import_batch; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.diagnostic_import_batch (
    id integer NOT NULL,
    session_id integer NOT NULL,
    import_kind character varying(30) NOT NULL,
    filename character varying(255),
    file_hash character varying(64),
    status character varying(30) NOT NULL,
    notes text,
    created_by integer,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: diagnostic_import_batch_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.diagnostic_import_batch_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: diagnostic_import_batch_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.diagnostic_import_batch_id_seq OWNED BY public.diagnostic_import_batch.id;


--
-- Name: diagnostic_import_issue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.diagnostic_import_issue (
    id integer NOT NULL,
    session_id integer NOT NULL,
    import_batch_id integer,
    severity character varying(20) NOT NULL,
    issue_type character varying(50) NOT NULL,
    message text NOT NULL,
    payload_json text,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: diagnostic_import_issue_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.diagnostic_import_issue_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: diagnostic_import_issue_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.diagnostic_import_issue_id_seq OWNED BY public.diagnostic_import_issue.id;


--
-- Name: diagnostic_kes_result; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.diagnostic_kes_result (
    id integer NOT NULL,
    session_id integer NOT NULL,
    import_batch_id integer,
    class_name_raw character varying(50),
    kes_code character varying(100) NOT NULL,
    kes_name character varying(1000),
    class_percent double precision,
    city_percent double precision,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: diagnostic_kes_result_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.diagnostic_kes_result_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: diagnostic_kes_result_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.diagnostic_kes_result_id_seq OWNED BY public.diagnostic_kes_result.id;


--
-- Name: diagnostic_result; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.diagnostic_result (
    id integer NOT NULL,
    session_id integer NOT NULL,
    child_id integer,
    school_class_id integer,
    import_batch_id integer,
    full_name_raw character varying(255),
    class_name_raw character varying(50),
    list_number integer,
    participant_code character varying(50),
    variant character varying(50),
    total_score double precision,
    percent double precision,
    mark character varying(20),
    level character varying(50),
    source_kind character varying(20) NOT NULL,
    is_final boolean NOT NULL,
    replaced_result_id integer,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: diagnostic_result_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.diagnostic_result_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: diagnostic_result_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.diagnostic_result_id_seq OWNED BY public.diagnostic_result.id;


--
-- Name: diagnostic_session; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.diagnostic_session (
    id integer NOT NULL,
    title character varying(255) NOT NULL,
    diagnostic_type character varying(30) NOT NULL,
    subject character varying(120),
    parallel integer,
    date_main date,
    date_reserve date,
    academic_year_id integer,
    status character varying(30) NOT NULL,
    created_by integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: diagnostic_session_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.diagnostic_session_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: diagnostic_session_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.diagnostic_session_id_seq OWNED BY public.diagnostic_session.id;


--
-- Name: diagnostic_student_code; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.diagnostic_student_code (
    id integer NOT NULL,
    session_id integer NOT NULL,
    child_id integer,
    school_class_id integer,
    full_name_raw character varying(255),
    class_name_raw character varying(50),
    participant_code character varying(50),
    list_number integer,
    source_type character varying(30),
    created_at timestamp without time zone NOT NULL
);


--
-- Name: diagnostic_student_code_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.diagnostic_student_code_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: diagnostic_student_code_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.diagnostic_student_code_id_seq OWNED BY public.diagnostic_student_code.id;


--
-- Name: diagnostic_task_result; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.diagnostic_task_result (
    id integer NOT NULL,
    result_id integer NOT NULL,
    task_number character varying(20) NOT NULL,
    raw_value character varying(50),
    topic character varying(500),
    skill character varying(500),
    kes_code character varying(100),
    block_name character varying(255),
    created_at timestamp without time zone NOT NULL
);


--
-- Name: diagnostic_task_result_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.diagnostic_task_result_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: diagnostic_task_result_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.diagnostic_task_result_id_seq OWNED BY public.diagnostic_task_result.id;


--
-- Name: diagnostic_teacher_binding; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.diagnostic_teacher_binding (
    id integer NOT NULL,
    result_id integer NOT NULL,
    teacher_id integer,
    source character varying(20) NOT NULL,
    comment character varying(500),
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: diagnostic_teacher_binding_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.diagnostic_teacher_binding_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: diagnostic_teacher_binding_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.diagnostic_teacher_binding_id_seq OWNED BY public.diagnostic_teacher_binding.id;


--
-- Name: document; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document (
    id integer NOT NULL,
    child_id integer NOT NULL,
    debt_id integer,
    academic_year_id integer,
    doc_type character varying(30) NOT NULL,
    doc_date date,
    original_name character varying(255) NOT NULL,
    stored_path character varying(500) NOT NULL,
    uploaded_by_user_id integer,
    uploaded_at timestamp without time zone NOT NULL,
    title character varying(255),
    filename character varying(255),
    retention_until date,
    is_archived boolean NOT NULL,
    is_hidden_by_retention boolean NOT NULL,
    is_deleted_soft boolean NOT NULL,
    deleted_at timestamp without time zone,
    deleted_by integer
);


--
-- Name: document_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.document_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: document_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.document_id_seq OWNED BY public.document.id;


--
-- Name: document_registry_access; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_registry_access (
    id integer NOT NULL,
    registry_type character varying(20) NOT NULL,
    user_id integer NOT NULL,
    access_type character varying(20) NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: document_registry_access_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.document_registry_access_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: document_registry_access_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.document_registry_access_id_seq OWNED BY public.document_registry_access.id;


--
-- Name: document_registry_record; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_registry_record (
    id integer NOT NULL,
    registry_type character varying(20) NOT NULL,
    number character varying(80) NOT NULL,
    doc_date date NOT NULL,
    subject character varying(500) NOT NULL,
    correspondent character varying(255),
    delivery_method character varying(120),
    responsible_user_id integer,
    status character varying(40) NOT NULL,
    notes text,
    created_by_id integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: document_registry_record_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.document_registry_record_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: document_registry_record_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.document_registry_record_id_seq OWNED BY public.document_registry_record.id;


--
-- Name: drive_item; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.drive_item (
    id integer NOT NULL,
    owner_user_id integer NOT NULL,
    parent_id integer,
    kind character varying(10) NOT NULL,
    scope character varying(10) NOT NULL,
    name character varying(255) NOT NULL,
    mime character varying(120),
    size_bytes bigint NOT NULL,
    storage_path character varying(500),
    ext character varying(20),
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    deleted_at timestamp without time zone
);


--
-- Name: drive_item_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.drive_item_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: drive_item_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.drive_item_id_seq OWNED BY public.drive_item.id;


--
-- Name: familiarization; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.familiarization (
    id integer NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    deadline_at timestamp without time zone,
    status character varying(30) DEFAULT 'active'::character varying NOT NULL,
    author_user_id integer,
    original_filename character varying(255),
    stored_filename character varying(255),
    content_type character varying(120),
    file_size integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: familiarization_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.familiarization_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: familiarization_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.familiarization_id_seq OWNED BY public.familiarization.id;


--
-- Name: familiarization_recipient; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.familiarization_recipient (
    id integer NOT NULL,
    familiarization_id integer NOT NULL,
    user_id integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    acknowledged_at timestamp without time zone
);


--
-- Name: familiarization_recipient_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.familiarization_recipient_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: familiarization_recipient_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.familiarization_recipient_id_seq OWNED BY public.familiarization_recipient.id;


--
-- Name: file_collection; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.file_collection (
    id integer NOT NULL,
    owner_user_id integer NOT NULL,
    title character varying(200) NOT NULL,
    description text,
    max_files_per_user integer NOT NULL,
    deadline_at timestamp without time zone NOT NULL,
    allow_late boolean DEFAULT true NOT NULL,
    status character varying(20) NOT NULL,
    created_at timestamp without time zone NOT NULL,
    closed_at timestamp without time zone
);


--
-- Name: file_collection_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.file_collection_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: file_collection_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.file_collection_id_seq OWNED BY public.file_collection.id;


--
-- Name: file_collection_submission; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.file_collection_submission (
    id integer NOT NULL,
    collection_id integer NOT NULL,
    user_id integer NOT NULL,
    file_name character varying(255) NOT NULL,
    storage_path character varying(500) NOT NULL,
    mime character varying(120),
    size_bytes bigint NOT NULL,
    ext character varying(20),
    created_at timestamp without time zone NOT NULL
);


--
-- Name: file_collection_submission_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.file_collection_submission_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: file_collection_submission_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.file_collection_submission_id_seq OWNED BY public.file_collection_submission.id;


--
-- Name: file_collection_target; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.file_collection_target (
    id integer NOT NULL,
    collection_id integer NOT NULL,
    role_code character varying(40),
    user_id integer
);


--
-- Name: file_collection_target_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.file_collection_target_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: file_collection_target_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.file_collection_target_id_seq OWNED BY public.file_collection_target.id;


--
-- Name: incident; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.incident (
    id integer NOT NULL,
    occurred_at timestamp without time zone NOT NULL,
    category character varying(50) NOT NULL,
    description text,
    status character varying(20) DEFAULT 'new'::character varying NOT NULL,
    created_at timestamp without time zone NOT NULL,
    author_id integer,
    assignee_id integer
);


--
-- Name: incident_assignee; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.incident_assignee (
    incident_id integer NOT NULL,
    user_id integer NOT NULL,
    added_at timestamp without time zone NOT NULL,
    added_by_id integer
);


--
-- Name: incident_assignment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.incident_assignment (
    id integer NOT NULL,
    incident_id integer NOT NULL,
    from_user_id integer,
    to_user_id integer,
    assigned_by_id integer,
    note text,
    assigned_at timestamp without time zone NOT NULL,
    ended_at timestamp without time zone
);


--
-- Name: incident_assignment_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.incident_assignment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: incident_assignment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.incident_assignment_id_seq OWNED BY public.incident_assignment.id;


--
-- Name: incident_child; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.incident_child (
    id integer NOT NULL,
    incident_id integer NOT NULL,
    child_id integer NOT NULL
);


--
-- Name: incident_child_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.incident_child_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: incident_child_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.incident_child_id_seq OWNED BY public.incident_child.id;


--
-- Name: incident_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.incident_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: incident_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.incident_id_seq OWNED BY public.incident.id;


--
-- Name: incident_note; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.incident_note (
    id integer NOT NULL,
    incident_id integer NOT NULL,
    author_id integer NOT NULL,
    text text NOT NULL,
    created_at timestamp without time zone NOT NULL,
    parent_id integer
);


--
-- Name: incident_note_attachment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.incident_note_attachment (
    id integer NOT NULL,
    note_id integer NOT NULL,
    filename character varying(512) NOT NULL,
    stored_filename character varying(512) NOT NULL,
    file_path character varying(1024) NOT NULL,
    content_type character varying(255),
    file_size bigint,
    uploaded_by_user_id integer,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: incident_note_attachment_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.incident_note_attachment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: incident_note_attachment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.incident_note_attachment_id_seq OWNED BY public.incident_note_attachment.id;


--
-- Name: incident_note_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.incident_note_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: incident_note_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.incident_note_id_seq OWNED BY public.incident_note.id;


--
-- Name: incident_notification; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.incident_notification (
    id integer NOT NULL,
    incident_id integer NOT NULL,
    user_id integer NOT NULL,
    notification_type character varying(50) NOT NULL,
    title character varying(255) NOT NULL,
    message text NOT NULL,
    is_read boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    read_at timestamp without time zone
);


--
-- Name: incident_notification_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.incident_notification_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: incident_notification_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.incident_notification_id_seq OWNED BY public.incident_notification.id;


--
-- Name: incident_status_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.incident_status_history (
    id integer NOT NULL,
    incident_id integer NOT NULL,
    from_status character varying(20),
    to_status character varying(20) NOT NULL,
    changed_by_id integer,
    changed_at timestamp without time zone NOT NULL,
    comment text
);


--
-- Name: incident_status_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.incident_status_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: incident_status_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.incident_status_history_id_seq OWNED BY public.incident_status_history.id;


--
-- Name: iom_card; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.iom_card (
    id integer NOT NULL,
    child_id integer NOT NULL,
    academic_year_id integer NOT NULL,
    iom_type character varying(30) NOT NULL,
    status character varying(30) NOT NULL,
    student_fio character varying(255) NOT NULL,
    birth_date date,
    birth_year integer,
    education_level character varying(50),
    school_class_id integer,
    class_name character varying(100),
    parallel character varying(20),
    building_id integer,
    building_name character varying(120),
    ovz_status character varying(120),
    nosology character varying(255),
    aop_variant character varying(255),
    parent_info text,
    class_teacher_name character varying(255),
    support_staff_summary text,
    curator_user_id integer,
    curator_name character varying(255),
    sppiss_head_name character varying(255),
    director_name character varying(255),
    consent_mark character varying(255),
    agreed_at date,
    approved_at date,
    start_date date,
    end_date date,
    notes text,
    created_by_user_id integer,
    updated_by_user_id integer,
    agreed_by_user_id integer,
    approved_by_user_id integer,
    previous_card_id integer,
    archived_by_user_id integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    archived_at timestamp without time zone
);


--
-- Name: iom_card_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.iom_card_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: iom_card_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.iom_card_id_seq OWNED BY public.iom_card.id;


--
-- Name: iom_cyclegram_link; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.iom_cyclegram_link (
    id integer NOT NULL,
    correction_id integer NOT NULL,
    cyclegram_entry_id integer NOT NULL,
    sync_key character varying(255),
    synced_at timestamp without time zone NOT NULL,
    synced_by_user_id integer
);


--
-- Name: iom_cyclegram_link_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.iom_cyclegram_link_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: iom_cyclegram_link_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.iom_cyclegram_link_id_seq OWNED BY public.iom_cyclegram_link.id;


--
-- Name: iom_export_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.iom_export_log (
    id integer NOT NULL,
    iom_card_id integer NOT NULL,
    export_format character varying(10) NOT NULL,
    status_snapshot character varying(30),
    exported_by_user_id integer,
    exported_at timestamp without time zone NOT NULL
);


--
-- Name: iom_export_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.iom_export_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: iom_export_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.iom_export_log_id_seq OWNED BY public.iom_export_log.id;


--
-- Name: iom_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.iom_history (
    id integer NOT NULL,
    iom_card_id integer NOT NULL,
    action character varying(80) NOT NULL,
    comment text,
    created_by_user_id integer,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: iom_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.iom_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: iom_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.iom_history_id_seq OWNED BY public.iom_history.id;


--
-- Name: iom_import_session_schedule; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.iom_import_session_schedule (
    id integer NOT NULL,
    iom_card_id integer NOT NULL,
    filename character varying(255) NOT NULL,
    rows_loaded integer NOT NULL,
    imported_by_user_id integer,
    imported_at timestamp without time zone NOT NULL,
    comment character varying(255)
);


--
-- Name: iom_import_session_schedule_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.iom_import_session_schedule_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: iom_import_session_schedule_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.iom_import_session_schedule_id_seq OWNED BY public.iom_import_session_schedule.id;


--
-- Name: iom_monitoring_entry; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.iom_monitoring_entry (
    id integer NOT NULL,
    iom_card_id integer NOT NULL,
    period character varying(30) NOT NULL,
    block_code character varying(50) NOT NULL,
    payload_json text,
    updated_by_user_id integer,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: iom_monitoring_entry_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.iom_monitoring_entry_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: iom_monitoring_entry_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.iom_monitoring_entry_id_seq OWNED BY public.iom_monitoring_entry.id;


--
-- Name: iom_monitoring_template; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.iom_monitoring_template (
    id integer NOT NULL,
    iom_type character varying(30) NOT NULL,
    period character varying(30) NOT NULL,
    block_code character varying(50) NOT NULL,
    block_title character varying(255) NOT NULL,
    line_code character varying(80) NOT NULL,
    line_title character varying(255) NOT NULL,
    scale_type character varying(30) NOT NULL,
    is_enabled boolean NOT NULL,
    sort_order integer NOT NULL
);


--
-- Name: iom_monitoring_template_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.iom_monitoring_template_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: iom_monitoring_template_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.iom_monitoring_template_id_seq OWNED BY public.iom_monitoring_template.id;


--
-- Name: iom_schedule_correction; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.iom_schedule_correction (
    id integer NOT NULL,
    iom_card_id integer NOT NULL,
    specialist_id integer NOT NULL,
    weekday character varying(20) NOT NULL,
    start_time character varying(20) NOT NULL,
    end_time character varying(20) NOT NULL,
    course_name character varying(255) NOT NULL,
    notes character varying(255),
    created_by_user_id integer,
    updated_by_user_id integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: iom_schedule_correction_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.iom_schedule_correction_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: iom_schedule_correction_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.iom_schedule_correction_id_seq OWNED BY public.iom_schedule_correction.id;


--
-- Name: iom_schedule_lesson; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.iom_schedule_lesson (
    id integer NOT NULL,
    iom_card_id integer NOT NULL,
    weekday character varying(20) NOT NULL,
    start_time character varying(20) NOT NULL,
    subject_name character varying(255) NOT NULL,
    source_type character varying(20) NOT NULL,
    sort_order integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: iom_schedule_lesson_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.iom_schedule_lesson_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: iom_schedule_lesson_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.iom_schedule_lesson_id_seq OWNED BY public.iom_schedule_lesson.id;


--
-- Name: iom_section_data; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.iom_section_data (
    id integer NOT NULL,
    iom_card_id integer NOT NULL,
    section_code character varying(80) NOT NULL,
    section_title character varying(255) NOT NULL,
    payload_json text,
    created_by_user_id integer,
    updated_by_user_id integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: iom_section_data_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.iom_section_data_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: iom_section_data_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.iom_section_data_id_seq OWNED BY public.iom_section_data.id;


--
-- Name: iom_specialist_plan; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.iom_specialist_plan (
    id integer NOT NULL,
    iom_card_id integer NOT NULL,
    role_title character varying(150) NOT NULL,
    specialist_id integer,
    assignment_id integer,
    recommendation_text text,
    deficits_text text,
    resources_text text,
    tasks_text text,
    work_form character varying(255),
    sessions_per_week character varying(50),
    course_name character varying(255),
    frequency character varying(255),
    expected_result text,
    monitoring_terms character varying(255),
    comment text,
    sort_order integer NOT NULL,
    created_by_user_id integer,
    updated_by_user_id integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: iom_specialist_plan_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.iom_specialist_plan_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: iom_specialist_plan_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.iom_specialist_plan_id_seq OWNED BY public.iom_specialist_plan.id;


--
-- Name: knowledge_article; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.knowledge_article (
    id integer NOT NULL,
    title character varying(255) NOT NULL,
    body text,
    link character varying(1024),
    file_path character varying(512),
    kind character varying(20) NOT NULL,
    target_roles json NOT NULL,
    sort_order integer NOT NULL,
    is_published boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: knowledge_article_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.knowledge_article_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: knowledge_article_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.knowledge_article_id_seq OWNED BY public.knowledge_article.id;


--
-- Name: mail_settings_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mail_settings_log (
    id integer NOT NULL,
    action_type character varying(50) NOT NULL,
    recipient character varying(255),
    subject character varying(255),
    status character varying(50),
    error_text text,
    created_at timestamp without time zone NOT NULL,
    created_by_user_id integer
);


--
-- Name: mail_settings_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.mail_settings_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: mail_settings_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.mail_settings_log_id_seq OWNED BY public.mail_settings_log.id;


--
-- Name: max_binding; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.max_binding (
    id integer NOT NULL,
    user_id integer NOT NULL,
    code character varying(6) NOT NULL,
    status character varying(16) NOT NULL,
    max_chat_id bigint,
    max_full_name character varying(160),
    created_at timestamp without time zone NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    bound_at timestamp without time zone
);


--
-- Name: max_binding_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.max_binding_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: max_binding_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.max_binding_id_seq OWNED BY public.max_binding.id;


--
-- Name: mobile_push_token; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mobile_push_token (
    id integer NOT NULL,
    user_id integer NOT NULL,
    token text NOT NULL,
    platform character varying(20) NOT NULL,
    device_id character varying(128),
    app_version character varying(40),
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    last_seen_at timestamp without time zone NOT NULL
);


--
-- Name: mobile_push_token_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.mobile_push_token_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: mobile_push_token_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.mobile_push_token_id_seq OWNED BY public.mobile_push_token.id;


--
-- Name: olympiad_import_session; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.olympiad_import_session (
    id integer NOT NULL,
    academic_year_id integer,
    stage character varying(30) NOT NULL,
    subject_id integer,
    subject_name character varying(255),
    department_id integer,
    source_file_name character varying(255),
    imported_by integer,
    total_rows integer NOT NULL,
    school_rows integer NOT NULL,
    matched_rows integer NOT NULL,
    unmatched_rows integer NOT NULL,
    created_rows integer NOT NULL,
    updated_rows integer NOT NULL,
    duplicate_rows integer NOT NULL,
    error_rows integer NOT NULL,
    status character varying(30) NOT NULL,
    comment text,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: olympiad_import_session_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.olympiad_import_session_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: olympiad_import_session_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.olympiad_import_session_id_seq OWNED BY public.olympiad_import_session.id;


--
-- Name: olympiad_result; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.olympiad_result (
    id integer NOT NULL,
    academic_year_id integer NOT NULL,
    child_id integer NOT NULL,
    school_class_id integer,
    teacher_id integer,
    department_id integer,
    subject_id integer,
    subject_name character varying(255),
    stage character varying(30) NOT NULL,
    class_study_text character varying(50),
    class_participation_text character varying(50),
    score double precision,
    max_score double precision,
    percent double precision,
    status character varying(500),
    status_original text,
    status_group character varying(50),
    stage_group character varying(50),
    is_annulled boolean DEFAULT false NOT NULL,
    reason text,
    teacher_binding_status character varying(30),
    teacher_binding_source character varying(30),
    teacher_binding_reason text,
    olympiad_date date,
    publication_date date,
    school_login character varying(50),
    school_ekis character varying(50),
    school_name character varying(255),
    source_file_name character varying(255),
    source_sheet_name character varying(255),
    source_row_number integer,
    source_row_hash character varying(64),
    import_session_id integer,
    created_by integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    is_archived boolean NOT NULL
);


--
-- Name: olympiad_result_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.olympiad_result_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: olympiad_result_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.olympiad_result_id_seq OWNED BY public.olympiad_result.id;


--
-- Name: olympiad_stage_mapping; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.olympiad_stage_mapping (
    id integer NOT NULL,
    source_stage_name character varying(255) NOT NULL,
    system_stage_code character varying(30) NOT NULL,
    is_active boolean NOT NULL
);


--
-- Name: olympiad_stage_mapping_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.olympiad_stage_mapping_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: olympiad_stage_mapping_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.olympiad_stage_mapping_id_seq OWNED BY public.olympiad_stage_mapping.id;


--
-- Name: olympiad_subject_mapping; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.olympiad_subject_mapping (
    id integer NOT NULL,
    olympiad_subject_name character varying(255) NOT NULL,
    olympiad_name character varying(255),
    subject_id integer NOT NULL,
    linked_subject_ids text,
    department_id integer,
    grade_from integer,
    grade_to integer,
    priority integer NOT NULL,
    is_active boolean NOT NULL,
    comment text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: olympiad_subject_mapping_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.olympiad_subject_mapping_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: olympiad_subject_mapping_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.olympiad_subject_mapping_id_seq OWNED BY public.olympiad_subject_mapping.id;


--
-- Name: olympiad_unmatched_row; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.olympiad_unmatched_row (
    id integer NOT NULL,
    import_session_id integer NOT NULL,
    raw_fio character varying(255),
    raw_class_study character varying(50),
    raw_class_participation character varying(50),
    raw_score character varying(50),
    raw_status character varying(500),
    raw_reason text,
    raw_subject character varying(255),
    raw_stage character varying(100),
    raw_school_login character varying(50),
    raw_school_ekis character varying(50),
    raw_payload_json text,
    unmatched_reason character varying(255),
    maybe_left_school boolean NOT NULL,
    comment text,
    resolution_status character varying(30) NOT NULL,
    resolved_child_id integer,
    resolved_teacher_id integer,
    resolved_department_id integer,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: olympiad_unmatched_row_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.olympiad_unmatched_row_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: olympiad_unmatched_row_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.olympiad_unmatched_row_id_seq OWNED BY public.olympiad_unmatched_row.id;


--
-- Name: order_responsible; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.order_responsible (
    id integer NOT NULL,
    section character varying(50) NOT NULL,
    user_id integer NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: order_responsible_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.order_responsible_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: order_responsible_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.order_responsible_id_seq OWNED BY public.order_responsible.id;


--
-- Name: order_responsible_link; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.order_responsible_link (
    id integer NOT NULL,
    order_id integer NOT NULL,
    user_id integer NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: order_responsible_link_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.order_responsible_link_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: order_responsible_link_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.order_responsible_link_id_seq OWNED BY public.order_responsible_link.id;


--
-- Name: organization_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.organization_settings (
    id integer NOT NULL,
    parent_org_name character varying(255),
    full_name character varying(255),
    short_name character varying(255),
    legal_name character varying(255),
    city character varying(120),
    address character varying(255),
    postal_code character varying(20),
    phone character varying(64),
    fax character varying(64),
    email character varying(120),
    website character varying(255),
    okpo character varying(32),
    ogrn character varying(32),
    inn character varying(32),
    kpp character varying(32),
    director_name character varying(255),
    director_position character varying(255),
    logo_path character varying(500),
    emblem_path character varying(500),
    show_in_header boolean NOT NULL,
    service_description character varying(500),
    is_active boolean NOT NULL,
    olympiad_school_login character varying(80),
    olympiad_ekis_code character varying(80),
    olympiad_school_name character varying(255),
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: organization_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.organization_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: organization_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.organization_settings_id_seq OWNED BY public.organization_settings.id;


--
-- Name: page_visit; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.page_visit (
    id integer NOT NULL,
    user_id integer NOT NULL,
    endpoint character varying(200) NOT NULL,
    method character varying(10) NOT NULL,
    path character varying(500) NOT NULL,
    referrer_endpoint character varying(200),
    status_code integer NOT NULL,
    ts timestamp without time zone NOT NULL
);


--
-- Name: page_visit_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.page_visit_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: page_visit_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.page_visit_id_seq OWNED BY public.page_visit.id;


--
-- Name: parent; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.parent (
    id integer NOT NULL,
    fio character varying(255) NOT NULL,
    phone character varying(50),
    email character varying(120),
    address character varying(500),
    notes text,
    retention_until date,
    is_archived boolean NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: parent_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.parent_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: parent_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.parent_id_seq OWNED BY public.parent.id;


--
-- Name: password_reset_token; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.password_reset_token (
    id integer NOT NULL,
    user_id integer NOT NULL,
    token_hash character varying(64) NOT NULL,
    created_at timestamp without time zone NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    used_at timestamp without time zone,
    request_ip character varying(64)
);


--
-- Name: password_reset_token_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.password_reset_token_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: password_reset_token_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.password_reset_token_id_seq OWNED BY public.password_reset_token.id;


--
-- Name: preschool_attendance_record; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.preschool_attendance_record (
    id integer NOT NULL,
    upload_id integer NOT NULL,
    group_id integer,
    child_id integer,
    source_filename character varying(500),
    child_name character varying(255) NOT NULL,
    account_number character varying(100),
    missed_total integer NOT NULL,
    credited_days integer NOT NULL,
    payment_days integer NOT NULL,
    child_days integer NOT NULL,
    absence_reasons text,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: preschool_attendance_record_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.preschool_attendance_record_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: preschool_attendance_record_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.preschool_attendance_record_id_seq OWNED BY public.preschool_attendance_record.id;


--
-- Name: preschool_attendance_upload; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.preschool_attendance_upload (
    id integer NOT NULL,
    academic_year_id integer,
    month character varying(20),
    original_filename character varying(500),
    stored_filename character varying(500),
    status character varying(50) NOT NULL,
    comment text,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: preschool_attendance_upload_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.preschool_attendance_upload_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: preschool_attendance_upload_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.preschool_attendance_upload_id_seq OWNED BY public.preschool_attendance_upload.id;


--
-- Name: preschool_child; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.preschool_child (
    id integer NOT NULL,
    group_id integer,
    import_batch_id integer,
    last_name character varying(150) NOT NULL,
    first_name character varying(150) NOT NULL,
    middle_name character varying(150),
    birth_date date,
    personal_account character varying(100),
    reg_address character varying(700),
    living_address character varying(700),
    actual_address character varying(700),
    status character varying(50) NOT NULL,
    note text,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: preschool_child_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.preschool_child_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: preschool_child_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.preschool_child_id_seq OWNED BY public.preschool_child.id;


--
-- Name: preschool_child_movement; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.preschool_child_movement (
    id integer NOT NULL,
    child_id integer NOT NULL,
    movement_date date,
    movement_type character varying(80) NOT NULL,
    from_academic_year_id integer,
    to_academic_year_id integer,
    from_group_id integer,
    to_group_id integer,
    basis character varying(500),
    comment text,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: preschool_child_movement_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.preschool_child_movement_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: preschool_child_movement_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.preschool_child_movement_id_seq OWNED BY public.preschool_child_movement.id;


--
-- Name: preschool_children_import; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.preschool_children_import (
    id integer NOT NULL,
    academic_year_id integer,
    filename character varying(500),
    added_count integer NOT NULL,
    skipped_count integer NOT NULL,
    created_groups_count integer NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: preschool_children_import_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.preschool_children_import_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: preschool_children_import_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.preschool_children_import_id_seq OWNED BY public.preschool_children_import.id;


--
-- Name: preschool_group; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.preschool_group (
    id integer NOT NULL,
    academic_year_id integer,
    building_id integer,
    name character varying(255) NOT NULL,
    age_level character varying(100),
    teacher_user_id integer,
    teacher_name character varying(255),
    is_active boolean NOT NULL,
    is_archived boolean NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: preschool_group_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.preschool_group_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: preschool_group_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.preschool_group_id_seq OWNED BY public.preschool_group.id;


--
-- Name: preschool_representative; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.preschool_representative (
    id integer NOT NULL,
    child_id integer NOT NULL,
    relation character varying(100),
    full_name character varying(255) NOT NULL,
    phone character varying(100),
    email character varying(255),
    address character varying(500),
    note text,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: preschool_representative_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.preschool_representative_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: preschool_representative_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.preschool_representative_id_seq OWNED BY public.preschool_representative.id;


--
-- Name: role; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.role (
    id integer NOT NULL,
    code character varying(50) NOT NULL,
    name character varying(100) NOT NULL
);


--
-- Name: role_dashboard_block; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.role_dashboard_block (
    id integer NOT NULL,
    role_code character varying(64) NOT NULL,
    block_code character varying(100) NOT NULL,
    is_visible boolean NOT NULL,
    is_enabled boolean NOT NULL,
    access_level character varying(20) NOT NULL,
    display_order integer NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: role_dashboard_block_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.role_dashboard_block_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: role_dashboard_block_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.role_dashboard_block_id_seq OWNED BY public.role_dashboard_block.id;


--
-- Name: role_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.role_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: role_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.role_id_seq OWNED BY public.role.id;


--
-- Name: role_module_access; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.role_module_access (
    id integer NOT NULL,
    role_code character varying(64) NOT NULL,
    module_code character varying(100) NOT NULL,
    is_visible boolean NOT NULL,
    is_enabled boolean NOT NULL,
    access_level character varying(20) NOT NULL,
    display_order integer NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: role_module_access_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.role_module_access_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: role_module_access_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.role_module_access_id_seq OWNED BY public.role_module_access.id;


--
-- Name: role_quick_link_access; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.role_quick_link_access (
    id integer NOT NULL,
    role_code character varying(64) NOT NULL,
    quick_link_code character varying(100) NOT NULL,
    is_visible boolean NOT NULL,
    is_enabled boolean NOT NULL,
    access_level character varying(20) NOT NULL,
    display_order integer NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: role_quick_link_access_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.role_quick_link_access_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: role_quick_link_access_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.role_quick_link_access_id_seq OWNED BY public.role_quick_link_access.id;


--
-- Name: saved_view; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.saved_view (
    id integer NOT NULL,
    user_id integer NOT NULL,
    scope character varying(40) NOT NULL,
    name character varying(80) NOT NULL,
    qs character varying(1000) NOT NULL,
    sort_order integer NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: saved_view_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.saved_view_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: saved_view_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.saved_view_id_seq OWNED BY public.saved_view.id;


--
-- Name: school_class; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.school_class (
    id integer NOT NULL,
    academic_year_id integer NOT NULL,
    building_id integer,
    name character varying(20) NOT NULL,
    grade integer,
    letter character varying(10),
    max_students integer NOT NULL,
    teacher_user_id integer,
    is_active boolean NOT NULL,
    is_archived boolean NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: school_class_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.school_class_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: school_class_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.school_class_id_seq OWNED BY public.school_class.id;


--
-- Name: school_order; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.school_order (
    id integer NOT NULL,
    number character varying(50) NOT NULL,
    order_date date NOT NULL,
    title character varying(255) NOT NULL,
    section character varying(50) NOT NULL,
    executor character varying(255),
    author character varying(255),
    responsible_user_id integer,
    valid_until date,
    original_submitted boolean NOT NULL,
    approved_by_deputy boolean NOT NULL,
    notes text,
    created_by_id integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: school_order_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.school_order_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: school_order_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.school_order_id_seq OWNED BY public.school_order.id;


--
-- Name: school_plan_category; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.school_plan_category (
    id integer NOT NULL,
    name character varying(120) NOT NULL,
    code character varying(50),
    color character varying(20),
    text_color character varying(20),
    sort_order integer NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: school_plan_category_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.school_plan_category_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: school_plan_category_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.school_plan_category_id_seq OWNED BY public.school_plan_category.id;


--
-- Name: school_plan_direction; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.school_plan_direction (
    id integer NOT NULL,
    name character varying(120) NOT NULL,
    code character varying(50),
    color character varying(20),
    text_color character varying(20),
    sort_order integer NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: school_plan_direction_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.school_plan_direction_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: school_plan_direction_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.school_plan_direction_id_seq OWNED BY public.school_plan_direction.id;


--
-- Name: school_plan_event; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.school_plan_event (
    id integer NOT NULL,
    academic_year_id integer,
    title character varying(255) NOT NULL,
    short_title character varying(120),
    description text,
    start_date date NOT NULL,
    end_date date,
    period_type character varying(20) NOT NULL,
    direction_id integer,
    category_id integer,
    responsible_user_id integer,
    responsible_text character varying(255),
    location character varying(255),
    participants character varying(500),
    priority character varying(20) NOT NULL,
    status character varying(20) NOT NULL,
    color character varying(20),
    text_color character varying(20),
    visibility_level character varying(20) NOT NULL,
    building_id integer,
    class_id integer,
    created_by_user_id integer,
    updated_by_user_id integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    is_archived boolean NOT NULL
);


--
-- Name: school_plan_event_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.school_plan_event_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: school_plan_event_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.school_plan_event_id_seq OWNED BY public.school_plan_event.id;


--
-- Name: service_activity_type; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_activity_type (
    id integer NOT NULL,
    code character varying(120) NOT NULL,
    name character varying(255) NOT NULL,
    work_category character varying(30) NOT NULL,
    specialist_scope character varying(255),
    template_text character varying(255),
    requires_child boolean NOT NULL,
    requires_group boolean NOT NULL,
    is_group_activity boolean NOT NULL,
    is_active boolean NOT NULL,
    sort_order integer NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: service_activity_type_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_activity_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_activity_type_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_activity_type_id_seq OWNED BY public.service_activity_type.id;


--
-- Name: service_assignment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_assignment (
    id integer NOT NULL,
    child_id integer NOT NULL,
    specialist_id integer NOT NULL,
    building_id integer,
    role_title character varying(150),
    start_date date,
    end_date date,
    basis text,
    status character varying(20) NOT NULL,
    comment text,
    incident_id integer,
    created_by_user_id integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: service_assignment_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_assignment_history (
    id integer NOT NULL,
    assignment_id integer NOT NULL,
    changed_by_user_id integer,
    old_status character varying(20),
    new_status character varying(20),
    comment text,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: service_assignment_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_assignment_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_assignment_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_assignment_history_id_seq OWNED BY public.service_assignment_history.id;


--
-- Name: service_assignment_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_assignment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_assignment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_assignment_id_seq OWNED BY public.service_assignment.id;


--
-- Name: service_cyclegram; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_cyclegram (
    id integer NOT NULL,
    specialist_id integer NOT NULL,
    academic_year character varying(20) NOT NULL,
    title character varying(255),
    position_title character varying(150),
    rate_value double precision,
    status character varying(20) NOT NULL,
    buildings_text character varying(255),
    copied_from_cyclegram_id integer,
    created_by_user_id integer,
    updated_by_user_id integer,
    reviewer_comment text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: service_cyclegram_entry; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_cyclegram_entry (
    id integer NOT NULL,
    cyclegram_id integer NOT NULL,
    weekday integer NOT NULL,
    start_time character varying(5) NOT NULL,
    end_time character varying(5) NOT NULL,
    activity_type_id integer NOT NULL,
    description text,
    child_id integer,
    group_text character varying(255),
    work_category character varying(30) NOT NULL,
    minutes integer NOT NULL,
    building_id integer,
    comment text,
    minutes_adjusted boolean NOT NULL,
    adjustment_reason character varying(255),
    sort_order integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: service_cyclegram_entry_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_cyclegram_entry_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_cyclegram_entry_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_cyclegram_entry_id_seq OWNED BY public.service_cyclegram_entry.id;


--
-- Name: service_cyclegram_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_cyclegram_history (
    id integer NOT NULL,
    cyclegram_id integer NOT NULL,
    changed_by_user_id integer,
    action character varying(50) NOT NULL,
    old_status character varying(20),
    new_status character varying(20),
    comment text,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: service_cyclegram_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_cyclegram_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_cyclegram_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_cyclegram_history_id_seq OWNED BY public.service_cyclegram_history.id;


--
-- Name: service_cyclegram_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_cyclegram_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_cyclegram_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_cyclegram_id_seq OWNED BY public.service_cyclegram.id;


--
-- Name: service_import_unmatched_staff; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_import_unmatched_staff (
    id integer NOT NULL,
    source character varying(50) NOT NULL,
    import_filename character varying(255),
    source_session_key character varying(120),
    imported_at timestamp without time zone NOT NULL,
    staff_fio character varying(255) NOT NULL,
    normalized_fio character varying(255),
    username character varying(120),
    phone character varying(32),
    email character varying(120),
    role_hint character varying(120),
    details text,
    status character varying(30) NOT NULL,
    matched_user_id integer,
    matched_by_user_id integer,
    matched_at timestamp without time zone
);


--
-- Name: service_import_unmatched_staff_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_import_unmatched_staff_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_import_unmatched_staff_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_import_unmatched_staff_id_seq OWNED BY public.service_import_unmatched_staff.id;


--
-- Name: service_presentation; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_presentation (
    id integer NOT NULL,
    child_id integer NOT NULL,
    academic_year character varying(20) NOT NULL,
    basis character varying(40),
    initiator_user_id integer,
    methodist_user_id integer,
    status character varying(20) NOT NULL,
    title character varying(255),
    building_id integer,
    school_class_id integer,
    last_changed_by_user_id integer,
    ready_percent integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: service_presentation_block; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_presentation_block (
    id integer NOT NULL,
    presentation_id integer NOT NULL,
    block_code character varying(80) NOT NULL,
    title character varying(255) NOT NULL,
    sort_order integer NOT NULL,
    fill_mode character varying(30) NOT NULL,
    executor_user_id integer,
    executor_specialist_id integer,
    status character varying(20) NOT NULL,
    is_required boolean NOT NULL,
    hint_text text,
    recommended_text text,
    content_text text,
    reviewer_comment text,
    source_name character varying(120),
    source_updated_at timestamp without time zone,
    updated_by_user_id integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: service_presentation_block_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_presentation_block_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_presentation_block_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_presentation_block_id_seq OWNED BY public.service_presentation_block.id;


--
-- Name: service_presentation_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_presentation_history (
    id integer NOT NULL,
    presentation_id integer NOT NULL,
    block_id integer,
    user_id integer,
    action character varying(80) NOT NULL,
    comment text,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: service_presentation_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_presentation_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_presentation_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_presentation_history_id_seq OWNED BY public.service_presentation_history.id;


--
-- Name: service_presentation_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_presentation_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_presentation_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_presentation_id_seq OWNED BY public.service_presentation.id;


--
-- Name: service_rate_norm; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_rate_norm (
    id integer NOT NULL,
    specialization_id integer NOT NULL,
    building_id integer,
    effective_from date NOT NULL,
    children_per_rate double precision NOT NULL,
    category_coefficient double precision NOT NULL,
    weekly_hours_norm double precision NOT NULL,
    complexity_coefficient double precision NOT NULL,
    rounding_rule character varying(20) NOT NULL,
    is_active boolean NOT NULL,
    comment character varying(255),
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: service_rate_norm_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_rate_norm_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_rate_norm_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_rate_norm_id_seq OWNED BY public.service_rate_norm.id;


--
-- Name: service_responsible; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_responsible (
    id integer NOT NULL,
    specialist_id integer NOT NULL,
    assigned_by_user_id integer,
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: service_responsible_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_responsible_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_responsible_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_responsible_id_seq OWNED BY public.service_responsible.id;


--
-- Name: service_specialist; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_specialist (
    id integer NOT NULL,
    user_id integer,
    last_name character varying(120) NOT NULL,
    first_name character varying(120) NOT NULL,
    middle_name character varying(120),
    position_title character varying(150),
    rate_value double precision,
    is_active boolean NOT NULL,
    main_building_id integer,
    phone character varying(64),
    email character varying(120),
    admin_comment text,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: service_specialist_building; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_specialist_building (
    specialist_id integer NOT NULL,
    building_id integer NOT NULL,
    is_main boolean NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: service_specialist_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_specialist_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_specialist_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_specialist_id_seq OWNED BY public.service_specialist.id;


--
-- Name: service_specialist_specialization; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_specialist_specialization (
    specialist_id integer NOT NULL,
    specialization_id integer NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: service_specialization; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_specialization (
    id integer NOT NULL,
    code character varying(80) NOT NULL,
    name character varying(120) NOT NULL,
    sort_order integer NOT NULL,
    is_active boolean NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: service_specialization_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.service_specialization_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: service_specialization_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.service_specialization_id_seq OWNED BY public.service_specialization.id;


--
-- Name: subject; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.subject (
    id integer NOT NULL,
    name character varying(120) NOT NULL,
    short_name character varying(50)
);


--
-- Name: subject_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.subject_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: subject_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.subject_id_seq OWNED BY public.subject.id;


--
-- Name: support_case; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.support_case (
    id integer NOT NULL,
    child_id integer NOT NULL,
    academic_year_id integer,
    support_type character varying(50) NOT NULL,
    status character varying(30) NOT NULL,
    description text,
    created_by integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: support_case_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.support_case_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: support_case_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.support_case_id_seq OWNED BY public.support_case.id;


--
-- Name: system_email_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.system_email_settings (
    id integer NOT NULL,
    smtp_enabled boolean DEFAULT false,
    smtp_host character varying(255),
    smtp_port integer DEFAULT 465,
    smtp_use_ssl boolean DEFAULT true,
    smtp_use_tls boolean DEFAULT false,
    smtp_username character varying(255),
    smtp_password text,
    mail_sender_email character varying(255),
    mail_sender_name character varying(255),
    task_email_notifications_enabled boolean DEFAULT true,
    task_comment_email_enabled boolean DEFAULT true,
    task_deadline_email_enabled boolean DEFAULT true,
    email_last_test_at character varying(64),
    email_last_test_status text,
    created_at character varying(64),
    updated_at character varying(64)
);


--
-- Name: system_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.system_log (
    id integer NOT NULL,
    user_id integer,
    action character varying(100) NOT NULL,
    object_type character varying(100),
    object_id character varying(100),
    details text,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: system_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.system_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: system_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.system_log_id_seq OWNED BY public.system_log.id;


--
-- Name: system_mail_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.system_mail_settings (
    id integer NOT NULL,
    provider character varying(64),
    smtp_host character varying(255),
    smtp_port integer,
    smtp_username character varying(255),
    smtp_password character varying(255),
    sender_email character varying(255),
    use_ssl boolean NOT NULL,
    use_tls boolean NOT NULL,
    login_url character varying(500),
    is_active boolean NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by_user_id integer
);


--
-- Name: system_mail_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.system_mail_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: system_mail_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.system_mail_settings_id_seq OWNED BY public.system_mail_settings.id;


--
-- Name: task; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task (
    id integer NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    task_type_id integer,
    priority character varying(20) NOT NULL,
    status character varying(40) NOT NULL,
    creator_user_id integer NOT NULL,
    responsible_user_id integer NOT NULL,
    controller_user_id integer,
    child_id integer,
    class_id integer,
    academic_year_id integer,
    parent_task_id integer,
    incident_id integer,
    deadline_at timestamp without time zone,
    completed_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    result_text text,
    is_control_required boolean NOT NULL,
    is_private boolean NOT NULL
);


--
-- Name: task_attachment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_attachment (
    id integer NOT NULL,
    task_id integer NOT NULL,
    filename character varying(255) NOT NULL,
    stored_filename character varying(255) NOT NULL,
    file_path character varying(500) NOT NULL,
    content_type character varying(255),
    file_size integer NOT NULL,
    file_kind character varying(20) NOT NULL,
    uploaded_by_user_id integer NOT NULL,
    created_at timestamp without time zone NOT NULL,
    is_deleted boolean NOT NULL,
    deleted_at timestamp without time zone,
    deleted_by_user_id integer
);


--
-- Name: task_attachment_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_attachment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_attachment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_attachment_id_seq OWNED BY public.task_attachment.id;


--
-- Name: task_auto_rule; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_auto_rule (
    id integer NOT NULL,
    code character varying(100) NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    is_enabled boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: task_auto_rule_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_auto_rule_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_auto_rule_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_auto_rule_id_seq OWNED BY public.task_auto_rule.id;


--
-- Name: task_checklist_item; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_checklist_item (
    id integer NOT NULL,
    task_id integer NOT NULL,
    title character varying(255) NOT NULL,
    is_done boolean NOT NULL,
    sort_order integer NOT NULL,
    completed_at timestamp without time zone,
    completed_by_user_id integer,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: task_checklist_item_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_checklist_item_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_checklist_item_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_checklist_item_id_seq OWNED BY public.task_checklist_item.id;


--
-- Name: task_comment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_comment (
    id integer NOT NULL,
    task_id integer NOT NULL,
    author_user_id integer NOT NULL,
    comment_text text NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    is_system_comment boolean NOT NULL
);


--
-- Name: task_comment_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_comment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_comment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_comment_id_seq OWNED BY public.task_comment.id;


--
-- Name: task_email_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_email_log (
    id integer NOT NULL,
    task_id integer,
    user_id integer,
    notification_type character varying(50) NOT NULL,
    email_to character varying(255),
    subject character varying(255) NOT NULL,
    status character varying(30) NOT NULL,
    error_text text,
    created_at timestamp without time zone NOT NULL,
    sent_at timestamp without time zone
);


--
-- Name: task_email_log_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_email_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_email_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_email_log_id_seq OWNED BY public.task_email_log.id;


--
-- Name: task_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_history (
    id integer NOT NULL,
    task_id integer NOT NULL,
    actor_user_id integer,
    event_type character varying(50) NOT NULL,
    field_name character varying(50),
    old_value text,
    new_value text,
    message text NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: task_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_history_id_seq OWNED BY public.task_history.id;


--
-- Name: task_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_id_seq OWNED BY public.task.id;


--
-- Name: task_notification; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_notification (
    id integer NOT NULL,
    task_id integer NOT NULL,
    user_id integer NOT NULL,
    notification_type character varying(50) NOT NULL,
    title character varying(255) NOT NULL,
    message text NOT NULL,
    is_read boolean NOT NULL,
    is_important boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    read_at timestamp without time zone
);


--
-- Name: task_notification_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_notification_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_notification_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_notification_id_seq OWNED BY public.task_notification.id;


--
-- Name: task_participant; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_participant (
    id integer NOT NULL,
    task_id integer NOT NULL,
    user_id integer NOT NULL,
    role character varying(30) NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: task_participant_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_participant_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_participant_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_participant_id_seq OWNED BY public.task_participant.id;


--
-- Name: task_template; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_template (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    title_template character varying(255) NOT NULL,
    description_template text,
    task_type_id integer,
    priority character varying(20) NOT NULL,
    default_deadline_days integer,
    is_control_required boolean NOT NULL,
    is_active boolean NOT NULL,
    created_by_user_id integer,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: task_template_checklist_item; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_template_checklist_item (
    id integer NOT NULL,
    template_id integer NOT NULL,
    title character varying(255) NOT NULL,
    sort_order integer NOT NULL
);


--
-- Name: task_template_checklist_item_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_template_checklist_item_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_template_checklist_item_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_template_checklist_item_id_seq OWNED BY public.task_template_checklist_item.id;


--
-- Name: task_template_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_template_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_template_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_template_id_seq OWNED BY public.task_template.id;


--
-- Name: task_type; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_type (
    id integer NOT NULL,
    name character varying(120) NOT NULL,
    is_active boolean NOT NULL,
    sort_order integer NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: task_type_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.task_type_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: task_type_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.task_type_id_seq OWNED BY public.task_type.id;


--
-- Name: teacher_course; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.teacher_course (
    id integer NOT NULL,
    teacher_id integer NOT NULL,
    academic_year_id integer,
    title character varying(255) NOT NULL,
    provider character varying(255),
    hours double precision,
    start_date date,
    end_date date,
    notes text,
    retention_until date,
    is_archived boolean NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: teacher_course_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.teacher_course_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: teacher_course_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.teacher_course_id_seq OWNED BY public.teacher_course.id;


--
-- Name: teacher_load; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.teacher_load (
    id integer NOT NULL,
    teacher_id integer NOT NULL,
    subject_id integer,
    academic_year_id integer,
    department_id integer,
    building_id integer,
    class_name character varying(255),
    grade integer,
    group_name character varying(255),
    hours double precision NOT NULL,
    subject_name character varying(255),
    building_name character varying(255),
    source_sheet character varying(255),
    row_number integer,
    is_whole_class boolean NOT NULL,
    is_meta_group boolean NOT NULL,
    teacher_total_hours double precision,
    retention_until date,
    is_archived boolean NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: teacher_load_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.teacher_load_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: teacher_load_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.teacher_load_id_seq OWNED BY public.teacher_load.id;


--
-- Name: teacher_mcko_result; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.teacher_mcko_result (
    id integer NOT NULL,
    teacher_id integer NOT NULL,
    subject_id integer,
    academic_year_id integer,
    passed_at date,
    expires_at date,
    level character varying(120),
    result_text character varying(255),
    retention_until date,
    is_archived boolean NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: teacher_mcko_result_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.teacher_mcko_result_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: teacher_mcko_result_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.teacher_mcko_result_id_seq OWNED BY public.teacher_mcko_result.id;


--
-- Name: user; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."user" (
    id integer NOT NULL,
    username character varying(120) NOT NULL,
    last_name character varying(120),
    first_name character varying(120),
    middle_name character varying(120),
    password_hash character varying(255) NOT NULL,
    phone character varying(32),
    email character varying(120),
    role character varying(30) NOT NULL,
    is_active_user boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    employment_status character varying(30) NOT NULL,
    dismissal_date date,
    archived_at timestamp without time zone,
    last_login_at timestamp without time zone,
    last_seen_at timestamp without time zone,
    active_days_count integer DEFAULT 0 NOT NULL,
    notify_incident_mode character varying(20) DEFAULT 'all'::character varying NOT NULL,
    notify_task_mode character varying(20) DEFAULT 'all'::character varying NOT NULL,
    notification_delivery_channel character varying(20) DEFAULT 'both'::character varying NOT NULL,
    task_notifications_enabled boolean DEFAULT true NOT NULL,
    task_email_enabled boolean DEFAULT true NOT NULL,
    task_notify_only_important boolean DEFAULT false NOT NULL
);


--
-- Name: user_building; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_building (
    id integer NOT NULL,
    user_id integer NOT NULL,
    building_id integer NOT NULL,
    is_primary boolean NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: user_building_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_building_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_building_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_building_id_seq OWNED BY public.user_building.id;


--
-- Name: user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_id_seq OWNED BY public."user".id;


--
-- Name: user_import_row; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_import_row (
    id integer NOT NULL,
    session_id integer NOT NULL,
    row_num integer NOT NULL,
    username character varying(120),
    action character varying(30) NOT NULL,
    note character varying(255),
    user_id integer,
    previous_role character varying(30),
    previous_last_name character varying(120),
    previous_first_name character varying(120),
    previous_middle_name character varying(120),
    previous_phone character varying(32),
    previous_email character varying(120),
    previous_employment_status character varying(30),
    previous_is_active_user boolean,
    previous_archived_at timestamp without time zone,
    previous_dismissal_date date,
    password_was_changed boolean NOT NULL
);


--
-- Name: user_import_row_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_import_row_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_import_row_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_import_row_id_seq OWNED BY public.user_import_row.id;


--
-- Name: user_import_session; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_import_session (
    id integer NOT NULL,
    filename character varying(255) NOT NULL,
    imported_at timestamp without time zone NOT NULL,
    imported_by integer,
    rows_total integer NOT NULL,
    created_count integer NOT NULL,
    updated_count integer NOT NULL,
    skipped_count integer NOT NULL,
    duplicate_count integer NOT NULL,
    status character varying(30) NOT NULL,
    notes text,
    reverted_at timestamp without time zone,
    reverted_by integer
);


--
-- Name: user_import_session_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_import_session_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_import_session_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_import_session_id_seq OWNED BY public.user_import_session.id;


--
-- Name: user_role; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_role (
    user_id integer NOT NULL,
    role_id integer NOT NULL
);


--
-- Name: academic_year id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.academic_year ALTER COLUMN id SET DEFAULT nextval('public.academic_year_id_seq'::regclass);


--
-- Name: appeal id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appeal ALTER COLUMN id SET DEFAULT nextval('public.appeal_id_seq'::regclass);


--
-- Name: appeal_attachment id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appeal_attachment ALTER COLUMN id SET DEFAULT nextval('public.appeal_attachment_id_seq'::regclass);


--
-- Name: attendance_import_session id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_import_session ALTER COLUMN id SET DEFAULT nextval('public.attendance_import_session_id_seq'::regclass);


--
-- Name: attendance_late id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_late ALTER COLUMN id SET DEFAULT nextval('public.attendance_late_id_seq'::regclass);


--
-- Name: attendance_pass id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_pass ALTER COLUMN id SET DEFAULT nextval('public.attendance_pass_id_seq'::regclass);


--
-- Name: attendance_raw_entry id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_raw_entry ALTER COLUMN id SET DEFAULT nextval('public.attendance_raw_entry_id_seq'::regclass);


--
-- Name: attendance_schedule_rule id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_schedule_rule ALTER COLUMN id SET DEFAULT nextval('public.attendance_schedule_rule_id_seq'::regclass);


--
-- Name: attendance_schedule_rule_class id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_schedule_rule_class ALTER COLUMN id SET DEFAULT nextval('public.attendance_schedule_rule_class_id_seq'::regclass);


--
-- Name: attendance_school_day id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_school_day ALTER COLUMN id SET DEFAULT nextval('public.attendance_school_day_id_seq'::regclass);


--
-- Name: buildings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.buildings ALTER COLUMN id SET DEFAULT nextval('public.buildings_id_seq'::regclass);


--
-- Name: child id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child ALTER COLUMN id SET DEFAULT nextval('public.child_id_seq'::regclass);


--
-- Name: child_comments id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_comments ALTER COLUMN id SET DEFAULT nextval('public.child_comments_id_seq'::regclass);


--
-- Name: child_enrollment id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_enrollment ALTER COLUMN id SET DEFAULT nextval('public.child_enrollment_id_seq'::regclass);


--
-- Name: child_events id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_events ALTER COLUMN id SET DEFAULT nextval('public.child_events_id_seq'::regclass);


--
-- Name: child_movement id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_movement ALTER COLUMN id SET DEFAULT nextval('public.child_movement_id_seq'::regclass);


--
-- Name: child_parent id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_parent ALTER COLUMN id SET DEFAULT nextval('public.child_parent_id_seq'::regclass);


--
-- Name: child_social id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_social ALTER COLUMN id SET DEFAULT nextval('public.child_social_id_seq'::regclass);


--
-- Name: child_transfer_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_transfer_history ALTER COLUMN id SET DEFAULT nextval('public.child_transfer_history_id_seq'::regclass);


--
-- Name: class_rating_snapshot id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.class_rating_snapshot ALTER COLUMN id SET DEFAULT nextval('public.class_rating_snapshot_id_seq'::regclass);


--
-- Name: control_work id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work ALTER COLUMN id SET DEFAULT nextval('public.control_work_id_seq'::regclass);


--
-- Name: control_work_assignment id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_assignment ALTER COLUMN id SET DEFAULT nextval('public.control_work_assignment_id_seq'::regclass);


--
-- Name: control_work_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_log ALTER COLUMN id SET DEFAULT nextval('public.control_work_log_id_seq'::regclass);


--
-- Name: control_work_result id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_result ALTER COLUMN id SET DEFAULT nextval('public.control_work_result_id_seq'::regclass);


--
-- Name: control_work_task id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_task ALTER COLUMN id SET DEFAULT nextval('public.control_work_task_id_seq'::regclass);


--
-- Name: dashboard_block_catalog id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dashboard_block_catalog ALTER COLUMN id SET DEFAULT nextval('public.dashboard_block_catalog_id_seq'::regclass);


--
-- Name: debt id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.debt ALTER COLUMN id SET DEFAULT nextval('public.debt_id_seq'::regclass);


--
-- Name: department id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.department ALTER COLUMN id SET DEFAULT nextval('public.department_id_seq'::regclass);


--
-- Name: department_leader id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.department_leader ALTER COLUMN id SET DEFAULT nextval('public.department_leader_id_seq'::regclass);


--
-- Name: department_subject id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.department_subject ALTER COLUMN id SET DEFAULT nextval('public.department_subject_id_seq'::regclass);


--
-- Name: diagnostic_import_batch id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_import_batch ALTER COLUMN id SET DEFAULT nextval('public.diagnostic_import_batch_id_seq'::regclass);


--
-- Name: diagnostic_import_issue id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_import_issue ALTER COLUMN id SET DEFAULT nextval('public.diagnostic_import_issue_id_seq'::regclass);


--
-- Name: diagnostic_kes_result id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_kes_result ALTER COLUMN id SET DEFAULT nextval('public.diagnostic_kes_result_id_seq'::regclass);


--
-- Name: diagnostic_result id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_result ALTER COLUMN id SET DEFAULT nextval('public.diagnostic_result_id_seq'::regclass);


--
-- Name: diagnostic_session id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_session ALTER COLUMN id SET DEFAULT nextval('public.diagnostic_session_id_seq'::regclass);


--
-- Name: diagnostic_student_code id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_student_code ALTER COLUMN id SET DEFAULT nextval('public.diagnostic_student_code_id_seq'::regclass);


--
-- Name: diagnostic_task_result id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_task_result ALTER COLUMN id SET DEFAULT nextval('public.diagnostic_task_result_id_seq'::regclass);


--
-- Name: diagnostic_teacher_binding id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_teacher_binding ALTER COLUMN id SET DEFAULT nextval('public.diagnostic_teacher_binding_id_seq'::regclass);


--
-- Name: document id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document ALTER COLUMN id SET DEFAULT nextval('public.document_id_seq'::regclass);


--
-- Name: document_registry_access id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_registry_access ALTER COLUMN id SET DEFAULT nextval('public.document_registry_access_id_seq'::regclass);


--
-- Name: document_registry_record id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_registry_record ALTER COLUMN id SET DEFAULT nextval('public.document_registry_record_id_seq'::regclass);


--
-- Name: drive_item id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.drive_item ALTER COLUMN id SET DEFAULT nextval('public.drive_item_id_seq'::regclass);


--
-- Name: familiarization id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.familiarization ALTER COLUMN id SET DEFAULT nextval('public.familiarization_id_seq'::regclass);


--
-- Name: familiarization_recipient id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.familiarization_recipient ALTER COLUMN id SET DEFAULT nextval('public.familiarization_recipient_id_seq'::regclass);


--
-- Name: file_collection id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_collection ALTER COLUMN id SET DEFAULT nextval('public.file_collection_id_seq'::regclass);


--
-- Name: file_collection_submission id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_collection_submission ALTER COLUMN id SET DEFAULT nextval('public.file_collection_submission_id_seq'::regclass);


--
-- Name: file_collection_target id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_collection_target ALTER COLUMN id SET DEFAULT nextval('public.file_collection_target_id_seq'::regclass);


--
-- Name: incident id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident ALTER COLUMN id SET DEFAULT nextval('public.incident_id_seq'::regclass);


--
-- Name: incident_assignment id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_assignment ALTER COLUMN id SET DEFAULT nextval('public.incident_assignment_id_seq'::regclass);


--
-- Name: incident_child id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_child ALTER COLUMN id SET DEFAULT nextval('public.incident_child_id_seq'::regclass);


--
-- Name: incident_note id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_note ALTER COLUMN id SET DEFAULT nextval('public.incident_note_id_seq'::regclass);


--
-- Name: incident_note_attachment id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_note_attachment ALTER COLUMN id SET DEFAULT nextval('public.incident_note_attachment_id_seq'::regclass);


--
-- Name: incident_notification id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_notification ALTER COLUMN id SET DEFAULT nextval('public.incident_notification_id_seq'::regclass);


--
-- Name: incident_status_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_status_history ALTER COLUMN id SET DEFAULT nextval('public.incident_status_history_id_seq'::regclass);


--
-- Name: iom_card id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_card ALTER COLUMN id SET DEFAULT nextval('public.iom_card_id_seq'::regclass);


--
-- Name: iom_cyclegram_link id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_cyclegram_link ALTER COLUMN id SET DEFAULT nextval('public.iom_cyclegram_link_id_seq'::regclass);


--
-- Name: iom_export_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_export_log ALTER COLUMN id SET DEFAULT nextval('public.iom_export_log_id_seq'::regclass);


--
-- Name: iom_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_history ALTER COLUMN id SET DEFAULT nextval('public.iom_history_id_seq'::regclass);


--
-- Name: iom_import_session_schedule id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_import_session_schedule ALTER COLUMN id SET DEFAULT nextval('public.iom_import_session_schedule_id_seq'::regclass);


--
-- Name: iom_monitoring_entry id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_monitoring_entry ALTER COLUMN id SET DEFAULT nextval('public.iom_monitoring_entry_id_seq'::regclass);


--
-- Name: iom_monitoring_template id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_monitoring_template ALTER COLUMN id SET DEFAULT nextval('public.iom_monitoring_template_id_seq'::regclass);


--
-- Name: iom_schedule_correction id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_schedule_correction ALTER COLUMN id SET DEFAULT nextval('public.iom_schedule_correction_id_seq'::regclass);


--
-- Name: iom_schedule_lesson id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_schedule_lesson ALTER COLUMN id SET DEFAULT nextval('public.iom_schedule_lesson_id_seq'::regclass);


--
-- Name: iom_section_data id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_section_data ALTER COLUMN id SET DEFAULT nextval('public.iom_section_data_id_seq'::regclass);


--
-- Name: iom_specialist_plan id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_specialist_plan ALTER COLUMN id SET DEFAULT nextval('public.iom_specialist_plan_id_seq'::regclass);


--
-- Name: knowledge_article id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_article ALTER COLUMN id SET DEFAULT nextval('public.knowledge_article_id_seq'::regclass);


--
-- Name: mail_settings_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_settings_log ALTER COLUMN id SET DEFAULT nextval('public.mail_settings_log_id_seq'::regclass);


--
-- Name: max_binding id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.max_binding ALTER COLUMN id SET DEFAULT nextval('public.max_binding_id_seq'::regclass);


--
-- Name: mobile_push_token id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mobile_push_token ALTER COLUMN id SET DEFAULT nextval('public.mobile_push_token_id_seq'::regclass);


--
-- Name: olympiad_import_session id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_import_session ALTER COLUMN id SET DEFAULT nextval('public.olympiad_import_session_id_seq'::regclass);


--
-- Name: olympiad_result id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_result ALTER COLUMN id SET DEFAULT nextval('public.olympiad_result_id_seq'::regclass);


--
-- Name: olympiad_stage_mapping id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_stage_mapping ALTER COLUMN id SET DEFAULT nextval('public.olympiad_stage_mapping_id_seq'::regclass);


--
-- Name: olympiad_subject_mapping id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_subject_mapping ALTER COLUMN id SET DEFAULT nextval('public.olympiad_subject_mapping_id_seq'::regclass);


--
-- Name: olympiad_unmatched_row id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_unmatched_row ALTER COLUMN id SET DEFAULT nextval('public.olympiad_unmatched_row_id_seq'::regclass);


--
-- Name: order_responsible id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_responsible ALTER COLUMN id SET DEFAULT nextval('public.order_responsible_id_seq'::regclass);


--
-- Name: order_responsible_link id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_responsible_link ALTER COLUMN id SET DEFAULT nextval('public.order_responsible_link_id_seq'::regclass);


--
-- Name: organization_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_settings ALTER COLUMN id SET DEFAULT nextval('public.organization_settings_id_seq'::regclass);


--
-- Name: page_visit id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.page_visit ALTER COLUMN id SET DEFAULT nextval('public.page_visit_id_seq'::regclass);


--
-- Name: parent id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parent ALTER COLUMN id SET DEFAULT nextval('public.parent_id_seq'::regclass);


--
-- Name: password_reset_token id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_token ALTER COLUMN id SET DEFAULT nextval('public.password_reset_token_id_seq'::regclass);


--
-- Name: preschool_attendance_record id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_attendance_record ALTER COLUMN id SET DEFAULT nextval('public.preschool_attendance_record_id_seq'::regclass);


--
-- Name: preschool_attendance_upload id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_attendance_upload ALTER COLUMN id SET DEFAULT nextval('public.preschool_attendance_upload_id_seq'::regclass);


--
-- Name: preschool_child id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_child ALTER COLUMN id SET DEFAULT nextval('public.preschool_child_id_seq'::regclass);


--
-- Name: preschool_child_movement id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_child_movement ALTER COLUMN id SET DEFAULT nextval('public.preschool_child_movement_id_seq'::regclass);


--
-- Name: preschool_children_import id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_children_import ALTER COLUMN id SET DEFAULT nextval('public.preschool_children_import_id_seq'::regclass);


--
-- Name: preschool_group id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_group ALTER COLUMN id SET DEFAULT nextval('public.preschool_group_id_seq'::regclass);


--
-- Name: preschool_representative id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_representative ALTER COLUMN id SET DEFAULT nextval('public.preschool_representative_id_seq'::regclass);


--
-- Name: role id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role ALTER COLUMN id SET DEFAULT nextval('public.role_id_seq'::regclass);


--
-- Name: role_dashboard_block id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_dashboard_block ALTER COLUMN id SET DEFAULT nextval('public.role_dashboard_block_id_seq'::regclass);


--
-- Name: role_module_access id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_module_access ALTER COLUMN id SET DEFAULT nextval('public.role_module_access_id_seq'::regclass);


--
-- Name: role_quick_link_access id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_quick_link_access ALTER COLUMN id SET DEFAULT nextval('public.role_quick_link_access_id_seq'::regclass);


--
-- Name: saved_view id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.saved_view ALTER COLUMN id SET DEFAULT nextval('public.saved_view_id_seq'::regclass);


--
-- Name: school_class id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_class ALTER COLUMN id SET DEFAULT nextval('public.school_class_id_seq'::regclass);


--
-- Name: school_order id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_order ALTER COLUMN id SET DEFAULT nextval('public.school_order_id_seq'::regclass);


--
-- Name: school_plan_category id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_plan_category ALTER COLUMN id SET DEFAULT nextval('public.school_plan_category_id_seq'::regclass);


--
-- Name: school_plan_direction id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_plan_direction ALTER COLUMN id SET DEFAULT nextval('public.school_plan_direction_id_seq'::regclass);


--
-- Name: school_plan_event id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_plan_event ALTER COLUMN id SET DEFAULT nextval('public.school_plan_event_id_seq'::regclass);


--
-- Name: service_activity_type id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_activity_type ALTER COLUMN id SET DEFAULT nextval('public.service_activity_type_id_seq'::regclass);


--
-- Name: service_assignment id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_assignment ALTER COLUMN id SET DEFAULT nextval('public.service_assignment_id_seq'::regclass);


--
-- Name: service_assignment_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_assignment_history ALTER COLUMN id SET DEFAULT nextval('public.service_assignment_history_id_seq'::regclass);


--
-- Name: service_cyclegram id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_cyclegram ALTER COLUMN id SET DEFAULT nextval('public.service_cyclegram_id_seq'::regclass);


--
-- Name: service_cyclegram_entry id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_cyclegram_entry ALTER COLUMN id SET DEFAULT nextval('public.service_cyclegram_entry_id_seq'::regclass);


--
-- Name: service_cyclegram_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_cyclegram_history ALTER COLUMN id SET DEFAULT nextval('public.service_cyclegram_history_id_seq'::regclass);


--
-- Name: service_import_unmatched_staff id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_import_unmatched_staff ALTER COLUMN id SET DEFAULT nextval('public.service_import_unmatched_staff_id_seq'::regclass);


--
-- Name: service_presentation id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation ALTER COLUMN id SET DEFAULT nextval('public.service_presentation_id_seq'::regclass);


--
-- Name: service_presentation_block id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation_block ALTER COLUMN id SET DEFAULT nextval('public.service_presentation_block_id_seq'::regclass);


--
-- Name: service_presentation_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation_history ALTER COLUMN id SET DEFAULT nextval('public.service_presentation_history_id_seq'::regclass);


--
-- Name: service_rate_norm id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_rate_norm ALTER COLUMN id SET DEFAULT nextval('public.service_rate_norm_id_seq'::regclass);


--
-- Name: service_responsible id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_responsible ALTER COLUMN id SET DEFAULT nextval('public.service_responsible_id_seq'::regclass);


--
-- Name: service_specialist id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_specialist ALTER COLUMN id SET DEFAULT nextval('public.service_specialist_id_seq'::regclass);


--
-- Name: service_specialization id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_specialization ALTER COLUMN id SET DEFAULT nextval('public.service_specialization_id_seq'::regclass);


--
-- Name: subject id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subject ALTER COLUMN id SET DEFAULT nextval('public.subject_id_seq'::regclass);


--
-- Name: support_case id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_case ALTER COLUMN id SET DEFAULT nextval('public.support_case_id_seq'::regclass);


--
-- Name: system_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_log ALTER COLUMN id SET DEFAULT nextval('public.system_log_id_seq'::regclass);


--
-- Name: system_mail_settings id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_mail_settings ALTER COLUMN id SET DEFAULT nextval('public.system_mail_settings_id_seq'::regclass);


--
-- Name: task id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task ALTER COLUMN id SET DEFAULT nextval('public.task_id_seq'::regclass);


--
-- Name: task_attachment id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_attachment ALTER COLUMN id SET DEFAULT nextval('public.task_attachment_id_seq'::regclass);


--
-- Name: task_auto_rule id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_auto_rule ALTER COLUMN id SET DEFAULT nextval('public.task_auto_rule_id_seq'::regclass);


--
-- Name: task_checklist_item id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_checklist_item ALTER COLUMN id SET DEFAULT nextval('public.task_checklist_item_id_seq'::regclass);


--
-- Name: task_comment id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_comment ALTER COLUMN id SET DEFAULT nextval('public.task_comment_id_seq'::regclass);


--
-- Name: task_email_log id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_email_log ALTER COLUMN id SET DEFAULT nextval('public.task_email_log_id_seq'::regclass);


--
-- Name: task_history id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_history ALTER COLUMN id SET DEFAULT nextval('public.task_history_id_seq'::regclass);


--
-- Name: task_notification id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_notification ALTER COLUMN id SET DEFAULT nextval('public.task_notification_id_seq'::regclass);


--
-- Name: task_participant id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_participant ALTER COLUMN id SET DEFAULT nextval('public.task_participant_id_seq'::regclass);


--
-- Name: task_template id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_template ALTER COLUMN id SET DEFAULT nextval('public.task_template_id_seq'::regclass);


--
-- Name: task_template_checklist_item id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_template_checklist_item ALTER COLUMN id SET DEFAULT nextval('public.task_template_checklist_item_id_seq'::regclass);


--
-- Name: task_type id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_type ALTER COLUMN id SET DEFAULT nextval('public.task_type_id_seq'::regclass);


--
-- Name: teacher_course id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teacher_course ALTER COLUMN id SET DEFAULT nextval('public.teacher_course_id_seq'::regclass);


--
-- Name: teacher_load id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teacher_load ALTER COLUMN id SET DEFAULT nextval('public.teacher_load_id_seq'::regclass);


--
-- Name: teacher_mcko_result id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teacher_mcko_result ALTER COLUMN id SET DEFAULT nextval('public.teacher_mcko_result_id_seq'::regclass);


--
-- Name: user id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."user" ALTER COLUMN id SET DEFAULT nextval('public.user_id_seq'::regclass);


--
-- Name: user_building id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_building ALTER COLUMN id SET DEFAULT nextval('public.user_building_id_seq'::regclass);


--
-- Name: user_import_row id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_import_row ALTER COLUMN id SET DEFAULT nextval('public.user_import_row_id_seq'::regclass);


--
-- Name: user_import_session id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_import_session ALTER COLUMN id SET DEFAULT nextval('public.user_import_session_id_seq'::regclass);


--
-- Name: academic_year academic_year_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.academic_year
    ADD CONSTRAINT academic_year_name_key UNIQUE (name);


--
-- Name: academic_year academic_year_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.academic_year
    ADD CONSTRAINT academic_year_pkey PRIMARY KEY (id);



--
-- Name: appeal_attachment appeal_attachment_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appeal_attachment
    ADD CONSTRAINT appeal_attachment_pkey PRIMARY KEY (id);


--
-- Name: appeal appeal_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appeal
    ADD CONSTRAINT appeal_pkey PRIMARY KEY (id);


--
-- Name: attendance_import_session attendance_import_session_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_import_session
    ADD CONSTRAINT attendance_import_session_pkey PRIMARY KEY (id);


--
-- Name: attendance_late attendance_late_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_late
    ADD CONSTRAINT attendance_late_pkey PRIMARY KEY (id);


--
-- Name: attendance_pass attendance_pass_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_pass
    ADD CONSTRAINT attendance_pass_pkey PRIMARY KEY (id);


--
-- Name: attendance_raw_entry attendance_raw_entry_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_raw_entry
    ADD CONSTRAINT attendance_raw_entry_pkey PRIMARY KEY (id);


--
-- Name: attendance_schedule_rule_class attendance_schedule_rule_class_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_schedule_rule_class
    ADD CONSTRAINT attendance_schedule_rule_class_pkey PRIMARY KEY (id);


--
-- Name: attendance_schedule_rule attendance_schedule_rule_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_schedule_rule
    ADD CONSTRAINT attendance_schedule_rule_pkey PRIMARY KEY (id);


--
-- Name: attendance_school_day attendance_school_day_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_school_day
    ADD CONSTRAINT attendance_school_day_pkey PRIMARY KEY (id);


--
-- Name: buildings buildings_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.buildings
    ADD CONSTRAINT buildings_name_key UNIQUE (name);


--
-- Name: buildings buildings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.buildings
    ADD CONSTRAINT buildings_pkey PRIMARY KEY (id);


--
-- Name: child_comments child_comments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_comments
    ADD CONSTRAINT child_comments_pkey PRIMARY KEY (id);


--
-- Name: child_enrollment child_enrollment_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_enrollment
    ADD CONSTRAINT child_enrollment_pkey PRIMARY KEY (id);


--
-- Name: child_events child_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_events
    ADD CONSTRAINT child_events_pkey PRIMARY KEY (id);


--
-- Name: child_movement child_movement_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_movement
    ADD CONSTRAINT child_movement_pkey PRIMARY KEY (id);


--
-- Name: child_parent child_parent_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_parent
    ADD CONSTRAINT child_parent_pkey PRIMARY KEY (id);


--
-- Name: child child_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child
    ADD CONSTRAINT child_pkey PRIMARY KEY (id);


--
-- Name: child_social child_social_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_social
    ADD CONSTRAINT child_social_pkey PRIMARY KEY (id);


--
-- Name: child_transfer_history child_transfer_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_transfer_history
    ADD CONSTRAINT child_transfer_history_pkey PRIMARY KEY (id);


--
-- Name: class_rating_snapshot class_rating_snapshot_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.class_rating_snapshot
    ADD CONSTRAINT class_rating_snapshot_pkey PRIMARY KEY (id);


--
-- Name: control_work_assignment control_work_assignment_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_assignment
    ADD CONSTRAINT control_work_assignment_pkey PRIMARY KEY (id);


--
-- Name: control_work_log control_work_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_log
    ADD CONSTRAINT control_work_log_pkey PRIMARY KEY (id);


--
-- Name: control_work control_work_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work
    ADD CONSTRAINT control_work_pkey PRIMARY KEY (id);


--
-- Name: control_work_result control_work_result_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_result
    ADD CONSTRAINT control_work_result_pkey PRIMARY KEY (id);


--
-- Name: control_work_task control_work_task_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_task
    ADD CONSTRAINT control_work_task_pkey PRIMARY KEY (id);


--
-- Name: dashboard_block_catalog dashboard_block_catalog_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.dashboard_block_catalog
    ADD CONSTRAINT dashboard_block_catalog_pkey PRIMARY KEY (id);


--
-- Name: debt debt_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.debt
    ADD CONSTRAINT debt_pkey PRIMARY KEY (id);


--
-- Name: department department_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.department
    ADD CONSTRAINT department_code_key UNIQUE (code);


--
-- Name: department_leader department_leader_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.department_leader
    ADD CONSTRAINT department_leader_pkey PRIMARY KEY (id);


--
-- Name: department department_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.department
    ADD CONSTRAINT department_name_key UNIQUE (name);


--
-- Name: department department_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.department
    ADD CONSTRAINT department_pkey PRIMARY KEY (id);


--
-- Name: department_subject department_subject_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.department_subject
    ADD CONSTRAINT department_subject_pkey PRIMARY KEY (id);


--
-- Name: diagnostic_import_batch diagnostic_import_batch_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_import_batch
    ADD CONSTRAINT diagnostic_import_batch_pkey PRIMARY KEY (id);


--
-- Name: diagnostic_import_issue diagnostic_import_issue_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_import_issue
    ADD CONSTRAINT diagnostic_import_issue_pkey PRIMARY KEY (id);


--
-- Name: diagnostic_kes_result diagnostic_kes_result_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_kes_result
    ADD CONSTRAINT diagnostic_kes_result_pkey PRIMARY KEY (id);


--
-- Name: diagnostic_result diagnostic_result_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_result
    ADD CONSTRAINT diagnostic_result_pkey PRIMARY KEY (id);


--
-- Name: diagnostic_session diagnostic_session_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_session
    ADD CONSTRAINT diagnostic_session_pkey PRIMARY KEY (id);


--
-- Name: diagnostic_student_code diagnostic_student_code_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_student_code
    ADD CONSTRAINT diagnostic_student_code_pkey PRIMARY KEY (id);


--
-- Name: diagnostic_task_result diagnostic_task_result_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_task_result
    ADD CONSTRAINT diagnostic_task_result_pkey PRIMARY KEY (id);


--
-- Name: diagnostic_teacher_binding diagnostic_teacher_binding_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_teacher_binding
    ADD CONSTRAINT diagnostic_teacher_binding_pkey PRIMARY KEY (id);


--
-- Name: document document_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document
    ADD CONSTRAINT document_pkey PRIMARY KEY (id);


--
-- Name: document_registry_access document_registry_access_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_registry_access
    ADD CONSTRAINT document_registry_access_pkey PRIMARY KEY (id);


--
-- Name: document_registry_record document_registry_record_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_registry_record
    ADD CONSTRAINT document_registry_record_pkey PRIMARY KEY (id);


--
-- Name: drive_item drive_item_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.drive_item
    ADD CONSTRAINT drive_item_pkey PRIMARY KEY (id);


--
-- Name: familiarization familiarization_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.familiarization
    ADD CONSTRAINT familiarization_pkey PRIMARY KEY (id);


--
-- Name: familiarization_recipient familiarization_recipient_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.familiarization_recipient
    ADD CONSTRAINT familiarization_recipient_pkey PRIMARY KEY (id);


--
-- Name: file_collection file_collection_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_collection
    ADD CONSTRAINT file_collection_pkey PRIMARY KEY (id);


--
-- Name: file_collection_submission file_collection_submission_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_collection_submission
    ADD CONSTRAINT file_collection_submission_pkey PRIMARY KEY (id);


--
-- Name: file_collection_target file_collection_target_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_collection_target
    ADD CONSTRAINT file_collection_target_pkey PRIMARY KEY (id);


--
-- Name: incident_assignee incident_assignee_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_assignee
    ADD CONSTRAINT incident_assignee_pkey PRIMARY KEY (incident_id, user_id);


--
-- Name: incident_assignment incident_assignment_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_assignment
    ADD CONSTRAINT incident_assignment_pkey PRIMARY KEY (id);


--
-- Name: incident_child incident_child_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_child
    ADD CONSTRAINT incident_child_pkey PRIMARY KEY (id);


--
-- Name: incident_note_attachment incident_note_attachment_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_note_attachment
    ADD CONSTRAINT incident_note_attachment_pkey PRIMARY KEY (id);


--
-- Name: incident_note incident_note_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_note
    ADD CONSTRAINT incident_note_pkey PRIMARY KEY (id);


--
-- Name: incident_notification incident_notification_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_notification
    ADD CONSTRAINT incident_notification_pkey PRIMARY KEY (id);


--
-- Name: incident incident_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident
    ADD CONSTRAINT incident_pkey PRIMARY KEY (id);


--
-- Name: incident_status_history incident_status_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_status_history
    ADD CONSTRAINT incident_status_history_pkey PRIMARY KEY (id);


--
-- Name: iom_card iom_card_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_card
    ADD CONSTRAINT iom_card_pkey PRIMARY KEY (id);


--
-- Name: iom_cyclegram_link iom_cyclegram_link_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_cyclegram_link
    ADD CONSTRAINT iom_cyclegram_link_pkey PRIMARY KEY (id);


--
-- Name: iom_export_log iom_export_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_export_log
    ADD CONSTRAINT iom_export_log_pkey PRIMARY KEY (id);


--
-- Name: iom_history iom_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_history
    ADD CONSTRAINT iom_history_pkey PRIMARY KEY (id);


--
-- Name: iom_import_session_schedule iom_import_session_schedule_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_import_session_schedule
    ADD CONSTRAINT iom_import_session_schedule_pkey PRIMARY KEY (id);


--
-- Name: iom_monitoring_entry iom_monitoring_entry_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_monitoring_entry
    ADD CONSTRAINT iom_monitoring_entry_pkey PRIMARY KEY (id);


--
-- Name: iom_monitoring_template iom_monitoring_template_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_monitoring_template
    ADD CONSTRAINT iom_monitoring_template_pkey PRIMARY KEY (id);


--
-- Name: iom_schedule_correction iom_schedule_correction_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_schedule_correction
    ADD CONSTRAINT iom_schedule_correction_pkey PRIMARY KEY (id);


--
-- Name: iom_schedule_lesson iom_schedule_lesson_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_schedule_lesson
    ADD CONSTRAINT iom_schedule_lesson_pkey PRIMARY KEY (id);


--
-- Name: iom_section_data iom_section_data_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_section_data
    ADD CONSTRAINT iom_section_data_pkey PRIMARY KEY (id);


--
-- Name: iom_specialist_plan iom_specialist_plan_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_specialist_plan
    ADD CONSTRAINT iom_specialist_plan_pkey PRIMARY KEY (id);


--
-- Name: knowledge_article knowledge_article_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.knowledge_article
    ADD CONSTRAINT knowledge_article_pkey PRIMARY KEY (id);


--
-- Name: mail_settings_log mail_settings_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_settings_log
    ADD CONSTRAINT mail_settings_log_pkey PRIMARY KEY (id);


--
-- Name: max_binding max_binding_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.max_binding
    ADD CONSTRAINT max_binding_pkey PRIMARY KEY (id);


--
-- Name: mobile_push_token mobile_push_token_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mobile_push_token
    ADD CONSTRAINT mobile_push_token_pkey PRIMARY KEY (id);


--
-- Name: mobile_push_token mobile_push_token_token_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mobile_push_token
    ADD CONSTRAINT mobile_push_token_token_key UNIQUE (token);


--
-- Name: olympiad_import_session olympiad_import_session_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_import_session
    ADD CONSTRAINT olympiad_import_session_pkey PRIMARY KEY (id);


--
-- Name: olympiad_result olympiad_result_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_result
    ADD CONSTRAINT olympiad_result_pkey PRIMARY KEY (id);


--
-- Name: olympiad_stage_mapping olympiad_stage_mapping_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_stage_mapping
    ADD CONSTRAINT olympiad_stage_mapping_pkey PRIMARY KEY (id);


--
-- Name: olympiad_stage_mapping olympiad_stage_mapping_source_stage_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_stage_mapping
    ADD CONSTRAINT olympiad_stage_mapping_source_stage_name_key UNIQUE (source_stage_name);


--
-- Name: olympiad_subject_mapping olympiad_subject_mapping_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_subject_mapping
    ADD CONSTRAINT olympiad_subject_mapping_pkey PRIMARY KEY (id);


--
-- Name: olympiad_unmatched_row olympiad_unmatched_row_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_unmatched_row
    ADD CONSTRAINT olympiad_unmatched_row_pkey PRIMARY KEY (id);


--
-- Name: order_responsible_link order_responsible_link_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_responsible_link
    ADD CONSTRAINT order_responsible_link_pkey PRIMARY KEY (id);


--
-- Name: order_responsible order_responsible_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_responsible
    ADD CONSTRAINT order_responsible_pkey PRIMARY KEY (id);


--
-- Name: order_responsible order_responsible_section_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_responsible
    ADD CONSTRAINT order_responsible_section_key UNIQUE (section);


--
-- Name: organization_settings organization_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.organization_settings
    ADD CONSTRAINT organization_settings_pkey PRIMARY KEY (id);


--
-- Name: page_visit page_visit_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.page_visit
    ADD CONSTRAINT page_visit_pkey PRIMARY KEY (id);


--
-- Name: parent parent_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parent
    ADD CONSTRAINT parent_pkey PRIMARY KEY (id);


--
-- Name: password_reset_token password_reset_token_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_token
    ADD CONSTRAINT password_reset_token_pkey PRIMARY KEY (id);


--
-- Name: preschool_attendance_record preschool_attendance_record_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_attendance_record
    ADD CONSTRAINT preschool_attendance_record_pkey PRIMARY KEY (id);


--
-- Name: preschool_attendance_upload preschool_attendance_upload_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_attendance_upload
    ADD CONSTRAINT preschool_attendance_upload_pkey PRIMARY KEY (id);


--
-- Name: preschool_child_movement preschool_child_movement_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_child_movement
    ADD CONSTRAINT preschool_child_movement_pkey PRIMARY KEY (id);


--
-- Name: preschool_child preschool_child_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_child
    ADD CONSTRAINT preschool_child_pkey PRIMARY KEY (id);


--
-- Name: preschool_children_import preschool_children_import_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_children_import
    ADD CONSTRAINT preschool_children_import_pkey PRIMARY KEY (id);


--
-- Name: preschool_group preschool_group_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_group
    ADD CONSTRAINT preschool_group_pkey PRIMARY KEY (id);


--
-- Name: preschool_representative preschool_representative_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_representative
    ADD CONSTRAINT preschool_representative_pkey PRIMARY KEY (id);


--
-- Name: role role_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role
    ADD CONSTRAINT role_code_key UNIQUE (code);


--
-- Name: role_dashboard_block role_dashboard_block_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_dashboard_block
    ADD CONSTRAINT role_dashboard_block_pkey PRIMARY KEY (id);


--
-- Name: role_module_access role_module_access_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_module_access
    ADD CONSTRAINT role_module_access_pkey PRIMARY KEY (id);


--
-- Name: role role_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role
    ADD CONSTRAINT role_pkey PRIMARY KEY (id);


--
-- Name: role_quick_link_access role_quick_link_access_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_quick_link_access
    ADD CONSTRAINT role_quick_link_access_pkey PRIMARY KEY (id);


--
-- Name: saved_view saved_view_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.saved_view
    ADD CONSTRAINT saved_view_pkey PRIMARY KEY (id);


--
-- Name: school_class school_class_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_class
    ADD CONSTRAINT school_class_pkey PRIMARY KEY (id);


--
-- Name: school_order school_order_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_order
    ADD CONSTRAINT school_order_pkey PRIMARY KEY (id);


--
-- Name: school_plan_category school_plan_category_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_plan_category
    ADD CONSTRAINT school_plan_category_code_key UNIQUE (code);


--
-- Name: school_plan_category school_plan_category_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_plan_category
    ADD CONSTRAINT school_plan_category_name_key UNIQUE (name);


--
-- Name: school_plan_category school_plan_category_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_plan_category
    ADD CONSTRAINT school_plan_category_pkey PRIMARY KEY (id);


--
-- Name: school_plan_direction school_plan_direction_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_plan_direction
    ADD CONSTRAINT school_plan_direction_code_key UNIQUE (code);


--
-- Name: school_plan_direction school_plan_direction_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_plan_direction
    ADD CONSTRAINT school_plan_direction_name_key UNIQUE (name);


--
-- Name: school_plan_direction school_plan_direction_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_plan_direction
    ADD CONSTRAINT school_plan_direction_pkey PRIMARY KEY (id);


--
-- Name: school_plan_event school_plan_event_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_plan_event
    ADD CONSTRAINT school_plan_event_pkey PRIMARY KEY (id);


--
-- Name: service_activity_type service_activity_type_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_activity_type
    ADD CONSTRAINT service_activity_type_pkey PRIMARY KEY (id);


--
-- Name: service_assignment_history service_assignment_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_assignment_history
    ADD CONSTRAINT service_assignment_history_pkey PRIMARY KEY (id);


--
-- Name: service_assignment service_assignment_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_assignment
    ADD CONSTRAINT service_assignment_pkey PRIMARY KEY (id);


--
-- Name: service_cyclegram_entry service_cyclegram_entry_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_cyclegram_entry
    ADD CONSTRAINT service_cyclegram_entry_pkey PRIMARY KEY (id);


--
-- Name: service_cyclegram_history service_cyclegram_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_cyclegram_history
    ADD CONSTRAINT service_cyclegram_history_pkey PRIMARY KEY (id);


--
-- Name: service_cyclegram service_cyclegram_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_cyclegram
    ADD CONSTRAINT service_cyclegram_pkey PRIMARY KEY (id);


--
-- Name: service_import_unmatched_staff service_import_unmatched_staff_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_import_unmatched_staff
    ADD CONSTRAINT service_import_unmatched_staff_pkey PRIMARY KEY (id);


--
-- Name: service_presentation_block service_presentation_block_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation_block
    ADD CONSTRAINT service_presentation_block_pkey PRIMARY KEY (id);


--
-- Name: service_presentation_history service_presentation_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation_history
    ADD CONSTRAINT service_presentation_history_pkey PRIMARY KEY (id);


--
-- Name: service_presentation service_presentation_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation
    ADD CONSTRAINT service_presentation_pkey PRIMARY KEY (id);


--
-- Name: service_rate_norm service_rate_norm_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_rate_norm
    ADD CONSTRAINT service_rate_norm_pkey PRIMARY KEY (id);


--
-- Name: service_responsible service_responsible_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_responsible
    ADD CONSTRAINT service_responsible_pkey PRIMARY KEY (id);


--
-- Name: service_specialist_building service_specialist_building_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_specialist_building
    ADD CONSTRAINT service_specialist_building_pkey PRIMARY KEY (specialist_id, building_id);


--
-- Name: service_specialist service_specialist_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_specialist
    ADD CONSTRAINT service_specialist_pkey PRIMARY KEY (id);


--
-- Name: service_specialist_specialization service_specialist_specialization_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_specialist_specialization
    ADD CONSTRAINT service_specialist_specialization_pkey PRIMARY KEY (specialist_id, specialization_id);


--
-- Name: service_specialization service_specialization_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_specialization
    ADD CONSTRAINT service_specialization_name_key UNIQUE (name);


--
-- Name: service_specialization service_specialization_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_specialization
    ADD CONSTRAINT service_specialization_pkey PRIMARY KEY (id);


--
-- Name: subject subject_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subject
    ADD CONSTRAINT subject_name_key UNIQUE (name);


--
-- Name: subject subject_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.subject
    ADD CONSTRAINT subject_pkey PRIMARY KEY (id);


--
-- Name: support_case support_case_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_case
    ADD CONSTRAINT support_case_pkey PRIMARY KEY (id);


--
-- Name: system_email_settings system_email_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_email_settings
    ADD CONSTRAINT system_email_settings_pkey PRIMARY KEY (id);


--
-- Name: system_log system_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_log
    ADD CONSTRAINT system_log_pkey PRIMARY KEY (id);


--
-- Name: system_mail_settings system_mail_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_mail_settings
    ADD CONSTRAINT system_mail_settings_pkey PRIMARY KEY (id);


--
-- Name: task_attachment task_attachment_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_attachment
    ADD CONSTRAINT task_attachment_pkey PRIMARY KEY (id);


--
-- Name: task_auto_rule task_auto_rule_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_auto_rule
    ADD CONSTRAINT task_auto_rule_code_key UNIQUE (code);


--
-- Name: task_auto_rule task_auto_rule_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_auto_rule
    ADD CONSTRAINT task_auto_rule_pkey PRIMARY KEY (id);


--
-- Name: task_checklist_item task_checklist_item_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_checklist_item
    ADD CONSTRAINT task_checklist_item_pkey PRIMARY KEY (id);


--
-- Name: task_comment task_comment_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_comment
    ADD CONSTRAINT task_comment_pkey PRIMARY KEY (id);


--
-- Name: task_email_log task_email_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_email_log
    ADD CONSTRAINT task_email_log_pkey PRIMARY KEY (id);


--
-- Name: task_history task_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_history
    ADD CONSTRAINT task_history_pkey PRIMARY KEY (id);


--
-- Name: task_notification task_notification_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_notification
    ADD CONSTRAINT task_notification_pkey PRIMARY KEY (id);


--
-- Name: task_participant task_participant_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_participant
    ADD CONSTRAINT task_participant_pkey PRIMARY KEY (id);


--
-- Name: task task_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task
    ADD CONSTRAINT task_pkey PRIMARY KEY (id);


--
-- Name: task_template_checklist_item task_template_checklist_item_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_template_checklist_item
    ADD CONSTRAINT task_template_checklist_item_pkey PRIMARY KEY (id);


--
-- Name: task_template task_template_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_template
    ADD CONSTRAINT task_template_name_key UNIQUE (name);


--
-- Name: task_template task_template_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_template
    ADD CONSTRAINT task_template_pkey PRIMARY KEY (id);


--
-- Name: task_type task_type_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_type
    ADD CONSTRAINT task_type_name_key UNIQUE (name);


--
-- Name: task_type task_type_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_type
    ADD CONSTRAINT task_type_pkey PRIMARY KEY (id);


--
-- Name: teacher_course teacher_course_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teacher_course
    ADD CONSTRAINT teacher_course_pkey PRIMARY KEY (id);


--
-- Name: teacher_load teacher_load_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teacher_load
    ADD CONSTRAINT teacher_load_pkey PRIMARY KEY (id);


--
-- Name: teacher_mcko_result teacher_mcko_result_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teacher_mcko_result
    ADD CONSTRAINT teacher_mcko_result_pkey PRIMARY KEY (id);


--
-- Name: child_parent uq_child_parent_relation; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_parent
    ADD CONSTRAINT uq_child_parent_relation UNIQUE (child_id, parent_id, relation_type);


--
-- Name: class_rating_snapshot uq_class_rating_year; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.class_rating_snapshot
    ADD CONSTRAINT uq_class_rating_year UNIQUE (class_name, year_label);


--
-- Name: department_subject uq_department_subject; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.department_subject
    ADD CONSTRAINT uq_department_subject UNIQUE (department_id, subject_id);


--
-- Name: document_registry_access uq_document_registry_access; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_registry_access
    ADD CONSTRAINT uq_document_registry_access UNIQUE (registry_type, user_id, access_type);


--
-- Name: familiarization_recipient uq_familiarization_recipient_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.familiarization_recipient
    ADD CONSTRAINT uq_familiarization_recipient_user UNIQUE (familiarization_id, user_id);


--
-- Name: incident_child uq_incident_child; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_child
    ADD CONSTRAINT uq_incident_child UNIQUE (incident_id, child_id);


--
-- Name: iom_monitoring_entry uq_iom_monitoring_entry; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_monitoring_entry
    ADD CONSTRAINT uq_iom_monitoring_entry UNIQUE (iom_card_id, period, block_code);


--
-- Name: iom_section_data uq_iom_section_per_card; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_section_data
    ADD CONSTRAINT uq_iom_section_per_card UNIQUE (iom_card_id, section_code);


--
-- Name: order_responsible_link uq_order_responsible_link; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_responsible_link
    ADD CONSTRAINT uq_order_responsible_link UNIQUE (order_id, user_id);


--
-- Name: preschool_group uq_preschool_group_year_building_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_group
    ADD CONSTRAINT uq_preschool_group_year_building_name UNIQUE (academic_year_id, building_id, name);


--
-- Name: role_dashboard_block uq_role_dashboard_block_role_block; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_dashboard_block
    ADD CONSTRAINT uq_role_dashboard_block_role_block UNIQUE (role_code, block_code);


--
-- Name: role_module_access uq_role_module_access_role_module; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_module_access
    ADD CONSTRAINT uq_role_module_access_role_module UNIQUE (role_code, module_code);


--
-- Name: role_quick_link_access uq_role_quick_link_role_link; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.role_quick_link_access
    ADD CONSTRAINT uq_role_quick_link_role_link UNIQUE (role_code, quick_link_code);


--
-- Name: saved_view uq_saved_view_user_scope_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.saved_view
    ADD CONSTRAINT uq_saved_view_user_scope_name UNIQUE (user_id, scope, name);


--
-- Name: school_class uq_school_class_year_building_name; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_class
    ADD CONSTRAINT uq_school_class_year_building_name UNIQUE (academic_year_id, building_id, name);


--
-- Name: service_presentation_block uq_service_presentation_block; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation_block
    ADD CONSTRAINT uq_service_presentation_block UNIQUE (presentation_id, block_code);


--
-- Name: service_responsible uq_service_responsible_specialist; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_responsible
    ADD CONSTRAINT uq_service_responsible_specialist UNIQUE (specialist_id);


--
-- Name: user_building uq_user_building_pair; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_building
    ADD CONSTRAINT uq_user_building_pair UNIQUE (user_id, building_id);


--
-- Name: user_building user_building_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_building
    ADD CONSTRAINT user_building_pkey PRIMARY KEY (id);


--
-- Name: user_import_row user_import_row_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_import_row
    ADD CONSTRAINT user_import_row_pkey PRIMARY KEY (id);


--
-- Name: user_import_session user_import_session_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_import_session
    ADD CONSTRAINT user_import_session_pkey PRIMARY KEY (id);


--
-- Name: user user_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."user"
    ADD CONSTRAINT user_pkey PRIMARY KEY (id);


--
-- Name: user_role user_role_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_role
    ADD CONSTRAINT user_role_pkey PRIMARY KEY (user_id, role_id);


--
-- Name: user user_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."user"
    ADD CONSTRAINT user_username_key UNIQUE (username);


--
-- Name: ix_appeal_attachment_appeal_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appeal_attachment_appeal_id ON public.appeal_attachment USING btree (appeal_id);


--
-- Name: ix_appeal_attachment_uploaded_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appeal_attachment_uploaded_by_user_id ON public.appeal_attachment USING btree (uploaded_by_user_id);


--
-- Name: ix_appeal_channel; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appeal_channel ON public.appeal USING btree (channel);


--
-- Name: ix_appeal_creator_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appeal_creator_user_id ON public.appeal USING btree (creator_user_id);


--
-- Name: ix_appeal_deadline_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appeal_deadline_at ON public.appeal USING btree (deadline_at);


--
-- Name: ix_appeal_linked_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appeal_linked_task_id ON public.appeal USING btree (linked_task_id);


--
-- Name: ix_appeal_number; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appeal_number ON public.appeal USING btree (number);


--
-- Name: ix_appeal_received_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appeal_received_at ON public.appeal USING btree (received_at);


--
-- Name: ix_appeal_responsible_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appeal_responsible_user_id ON public.appeal USING btree (responsible_user_id);


--
-- Name: ix_appeal_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_appeal_status ON public.appeal USING btree (status);


--
-- Name: ix_attendance_import_session_building_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_import_session_building_id ON public.attendance_import_session USING btree (building_id);


--
-- Name: ix_attendance_import_session_imported_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_import_session_imported_at ON public.attendance_import_session USING btree (imported_at);


--
-- Name: ix_attendance_import_session_period_month; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_import_session_period_month ON public.attendance_import_session USING btree (period_month);


--
-- Name: ix_attendance_import_session_period_num; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_import_session_period_num ON public.attendance_import_session USING btree (period_num);


--
-- Name: ix_attendance_import_session_period_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_import_session_period_year ON public.attendance_import_session USING btree (period_year);


--
-- Name: ix_attendance_import_session_year_month; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_import_session_year_month ON public.attendance_import_session USING btree (period_year, period_num);


--
-- Name: ix_attendance_late_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_late_child_id ON public.attendance_late USING btree (child_id);


--
-- Name: ix_attendance_late_class_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_late_class_id ON public.attendance_late USING btree (class_id);


--
-- Name: ix_attendance_late_date_class; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_late_date_class ON public.attendance_late USING btree (late_date, class_id);


--
-- Name: ix_attendance_late_import_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_late_import_session_id ON public.attendance_late USING btree (import_session_id);


--
-- Name: ix_attendance_late_late_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_late_late_date ON public.attendance_late USING btree (late_date);


--
-- Name: ix_attendance_pass_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_pass_child_id ON public.attendance_pass USING btree (child_id);


--
-- Name: ix_attendance_pass_class_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_pass_class_id ON public.attendance_pass USING btree (class_id);


--
-- Name: ix_attendance_pass_pass_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_pass_pass_date ON public.attendance_pass USING btree (pass_date);


--
-- Name: ix_attendance_pass_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_pass_status ON public.attendance_pass USING btree (status);


--
-- Name: ix_attendance_raw_entry_child_entry_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_raw_entry_child_entry_date ON public.attendance_raw_entry USING btree (child_id, entry_date);


--
-- Name: ix_attendance_raw_entry_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_raw_entry_child_id ON public.attendance_raw_entry USING btree (child_id);


--
-- Name: ix_attendance_raw_entry_entry_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_raw_entry_entry_date ON public.attendance_raw_entry USING btree (entry_date);


--
-- Name: ix_attendance_raw_entry_entry_date_class; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_raw_entry_entry_date_class ON public.attendance_raw_entry USING btree (entry_date, matched_class_id);


--
-- Name: ix_attendance_raw_entry_full_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_raw_entry_full_name ON public.attendance_raw_entry USING btree (full_name);


--
-- Name: ix_attendance_raw_entry_import_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_raw_entry_import_session_id ON public.attendance_raw_entry USING btree (import_session_id);


--
-- Name: ix_attendance_raw_entry_is_late; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_raw_entry_is_late ON public.attendance_raw_entry USING btree (is_late);


--
-- Name: ix_attendance_raw_entry_matched_class_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_raw_entry_matched_class_id ON public.attendance_raw_entry USING btree (matched_class_id);


--
-- Name: ix_attendance_raw_entry_source_class_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_raw_entry_source_class_name ON public.attendance_raw_entry USING btree (source_class_name);


--
-- Name: ix_attendance_schedule_rule_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_schedule_rule_academic_year_id ON public.attendance_schedule_rule USING btree (academic_year_id);


--
-- Name: ix_attendance_schedule_rule_class_class_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_schedule_rule_class_class_id ON public.attendance_schedule_rule_class USING btree (class_id);


--
-- Name: ix_attendance_schedule_rule_class_rule_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_schedule_rule_class_rule_id ON public.attendance_schedule_rule_class USING btree (rule_id);


--
-- Name: ix_attendance_schedule_rule_grade; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_schedule_rule_grade ON public.attendance_schedule_rule USING btree (grade);


--
-- Name: ix_attendance_schedule_rule_school_class_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_schedule_rule_school_class_id ON public.attendance_schedule_rule USING btree (school_class_id);


--
-- Name: ix_attendance_school_day_day_date; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_attendance_school_day_day_date ON public.attendance_school_day USING btree (day_date);


--
-- Name: ix_attendance_school_day_month_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_attendance_school_day_month_key ON public.attendance_school_day USING btree (month_key);


--
-- Name: ix_child_comments_author_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_comments_author_id ON public.child_comments USING btree (author_id);


--
-- Name: ix_child_comments_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_comments_child_id ON public.child_comments USING btree (child_id);


--
-- Name: ix_child_enrollment_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_enrollment_academic_year_id ON public.child_enrollment USING btree (academic_year_id);


--
-- Name: ix_child_enrollment_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_enrollment_child_id ON public.child_enrollment USING btree (child_id);


--
-- Name: ix_child_enrollment_class_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_enrollment_class_status ON public.child_enrollment USING btree (school_class_id, status);


--
-- Name: ix_child_enrollment_school_class_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_enrollment_school_class_id ON public.child_enrollment USING btree (school_class_id);


--
-- Name: ix_child_enrollment_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_enrollment_status ON public.child_enrollment USING btree (status);


--
-- Name: ix_child_events_author_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_events_author_id ON public.child_events USING btree (author_id);


--
-- Name: ix_child_events_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_events_child_id ON public.child_events USING btree (child_id);


--
-- Name: ix_child_events_event_type_from_class; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_events_event_type_from_class ON public.child_events USING btree (event_type, from_class);


--
-- Name: ix_child_events_from_class; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_events_from_class ON public.child_events USING btree (from_class);


--
-- Name: ix_child_movement_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_movement_academic_year_id ON public.child_movement USING btree (academic_year_id);


--
-- Name: ix_child_movement_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_movement_child_id ON public.child_movement USING btree (child_id);


--
-- Name: ix_child_movement_movement_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_movement_movement_type ON public.child_movement USING btree (movement_type);


--
-- Name: ix_child_name_parts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_name_parts ON public.child USING btree (last_name, first_name, middle_name);


--
-- Name: ix_child_parent_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_parent_child_id ON public.child_parent USING btree (child_id);


--
-- Name: ix_child_parent_parent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_parent_parent_id ON public.child_parent USING btree (parent_id);


--
-- Name: ix_child_social_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_child_social_child_id ON public.child_social USING btree (child_id);


--
-- Name: ix_child_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_status ON public.child USING btree (status);


--
-- Name: ix_child_transfer_history_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_transfer_history_child_id ON public.child_transfer_history USING btree (child_id);


--
-- Name: ix_child_transfer_history_from_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_transfer_history_from_academic_year_id ON public.child_transfer_history USING btree (from_academic_year_id);


--
-- Name: ix_child_transfer_history_from_class_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_transfer_history_from_class_id ON public.child_transfer_history USING btree (from_class_id);


--
-- Name: ix_child_transfer_history_to_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_transfer_history_to_academic_year_id ON public.child_transfer_history USING btree (to_academic_year_id);


--
-- Name: ix_child_transfer_history_to_class_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_child_transfer_history_to_class_id ON public.child_transfer_history USING btree (to_class_id);


--
-- Name: ix_class_rating_snapshot_class_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_class_rating_snapshot_class_name ON public.class_rating_snapshot USING btree (class_name);


--
-- Name: ix_class_rating_snapshot_year_label; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_class_rating_snapshot_year_label ON public.class_rating_snapshot USING btree (year_label);


--
-- Name: ix_collection_submission_col_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_collection_submission_col_user ON public.file_collection_submission USING btree (collection_id, user_id);


--
-- Name: ix_control_work_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_control_work_academic_year_id ON public.control_work USING btree (academic_year_id);


--
-- Name: ix_control_work_assignment_control_work_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_control_work_assignment_control_work_id ON public.control_work_assignment USING btree (control_work_id);


--
-- Name: ix_control_work_assignment_school_class_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_control_work_assignment_school_class_id ON public.control_work_assignment USING btree (school_class_id);


--
-- Name: ix_control_work_assignment_teacher_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_control_work_assignment_teacher_id ON public.control_work_assignment USING btree (teacher_id);


--
-- Name: ix_control_work_log_control_work_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_control_work_log_control_work_id ON public.control_work_log USING btree (control_work_id);


--
-- Name: ix_control_work_log_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_control_work_log_created_at ON public.control_work_log USING btree (created_at);


--
-- Name: ix_control_work_log_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_control_work_log_event_type ON public.control_work_log USING btree (event_type);


--
-- Name: ix_control_work_log_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_control_work_log_user_id ON public.control_work_log USING btree (user_id);


--
-- Name: ix_control_work_result_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_control_work_result_academic_year_id ON public.control_work_result USING btree (academic_year_id);


--
-- Name: ix_control_work_result_assignment_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_control_work_result_assignment_id ON public.control_work_result USING btree (assignment_id);


--
-- Name: ix_control_work_result_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_control_work_result_child_id ON public.control_work_result USING btree (child_id);


--
-- Name: ix_control_work_result_control_work_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_control_work_result_control_work_id ON public.control_work_result USING btree (control_work_id);


--
-- Name: ix_control_work_result_school_class_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_control_work_result_school_class_id ON public.control_work_result USING btree (school_class_id);


--
-- Name: ix_control_work_subject_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_control_work_subject_id ON public.control_work USING btree (subject_id);


--
-- Name: ix_control_work_task_control_work_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_control_work_task_control_work_id ON public.control_work_task USING btree (control_work_id);


--
-- Name: ix_dashboard_block_catalog_block_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_dashboard_block_catalog_block_code ON public.dashboard_block_catalog USING btree (block_code);


--
-- Name: ix_dashboard_block_catalog_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dashboard_block_catalog_category ON public.dashboard_block_catalog USING btree (category);


--
-- Name: ix_dashboard_block_catalog_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_dashboard_block_catalog_is_active ON public.dashboard_block_catalog USING btree (is_active);


--
-- Name: ix_debt_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_debt_child_id ON public.debt USING btree (child_id);


--
-- Name: ix_debt_subject_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_debt_subject_id ON public.debt USING btree (subject_id);


--
-- Name: ix_department_leader_building_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_department_leader_building_id ON public.department_leader USING btree (building_id);


--
-- Name: ix_department_leader_department_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_department_leader_department_id ON public.department_leader USING btree (department_id);


--
-- Name: ix_department_leader_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_department_leader_user_id ON public.department_leader USING btree (user_id);


--
-- Name: ix_department_subject_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_department_subject_academic_year_id ON public.department_subject USING btree (academic_year_id);


--
-- Name: ix_department_subject_department_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_department_subject_department_id ON public.department_subject USING btree (department_id);


--
-- Name: ix_department_subject_subject_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_department_subject_subject_id ON public.department_subject USING btree (subject_id);


--
-- Name: ix_diagnostic_import_batch_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_import_batch_created_by ON public.diagnostic_import_batch USING btree (created_by);


--
-- Name: ix_diagnostic_import_batch_file_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_import_batch_file_hash ON public.diagnostic_import_batch USING btree (file_hash);


--
-- Name: ix_diagnostic_import_batch_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_import_batch_session_id ON public.diagnostic_import_batch USING btree (session_id);


--
-- Name: ix_diagnostic_import_issue_import_batch_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_import_issue_import_batch_id ON public.diagnostic_import_issue USING btree (import_batch_id);


--
-- Name: ix_diagnostic_import_issue_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_import_issue_session_id ON public.diagnostic_import_issue USING btree (session_id);


--
-- Name: ix_diagnostic_kes_result_import_batch_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_kes_result_import_batch_id ON public.diagnostic_kes_result USING btree (import_batch_id);


--
-- Name: ix_diagnostic_kes_result_kes_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_kes_result_kes_code ON public.diagnostic_kes_result USING btree (kes_code);


--
-- Name: ix_diagnostic_kes_result_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_kes_result_session_id ON public.diagnostic_kes_result USING btree (session_id);


--
-- Name: ix_diagnostic_result_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_result_child_id ON public.diagnostic_result USING btree (child_id);


--
-- Name: ix_diagnostic_result_import_batch_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_result_import_batch_id ON public.diagnostic_result USING btree (import_batch_id);


--
-- Name: ix_diagnostic_result_participant_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_result_participant_code ON public.diagnostic_result USING btree (participant_code);


--
-- Name: ix_diagnostic_result_school_class_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_result_school_class_id ON public.diagnostic_result USING btree (school_class_id);


--
-- Name: ix_diagnostic_result_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_result_session_id ON public.diagnostic_result USING btree (session_id);


--
-- Name: ix_diagnostic_session_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_session_academic_year_id ON public.diagnostic_session USING btree (academic_year_id);


--
-- Name: ix_diagnostic_session_created_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_session_created_by ON public.diagnostic_session USING btree (created_by);


--
-- Name: ix_diagnostic_student_code_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_student_code_child_id ON public.diagnostic_student_code USING btree (child_id);


--
-- Name: ix_diagnostic_student_code_participant_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_student_code_participant_code ON public.diagnostic_student_code USING btree (participant_code);


--
-- Name: ix_diagnostic_student_code_school_class_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_student_code_school_class_id ON public.diagnostic_student_code USING btree (school_class_id);


--
-- Name: ix_diagnostic_student_code_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_student_code_session_id ON public.diagnostic_student_code USING btree (session_id);


--
-- Name: ix_diagnostic_task_result_result_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_task_result_result_id ON public.diagnostic_task_result USING btree (result_id);


--
-- Name: ix_diagnostic_teacher_binding_result_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_diagnostic_teacher_binding_result_id ON public.diagnostic_teacher_binding USING btree (result_id);


--
-- Name: ix_diagnostic_teacher_binding_teacher_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_diagnostic_teacher_binding_teacher_id ON public.diagnostic_teacher_binding USING btree (teacher_id);


--
-- Name: ix_document_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_academic_year_id ON public.document USING btree (academic_year_id);


--
-- Name: ix_document_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_child_id ON public.document USING btree (child_id);


--
-- Name: ix_document_registry_access_access_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_registry_access_access_type ON public.document_registry_access USING btree (access_type);


--
-- Name: ix_document_registry_access_registry_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_registry_access_registry_type ON public.document_registry_access USING btree (registry_type);


--
-- Name: ix_document_registry_access_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_registry_access_user_id ON public.document_registry_access USING btree (user_id);


--
-- Name: ix_document_registry_record_doc_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_registry_record_doc_date ON public.document_registry_record USING btree (doc_date);


--
-- Name: ix_document_registry_record_number; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_registry_record_number ON public.document_registry_record USING btree (number);


--
-- Name: ix_document_registry_record_registry_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_registry_record_registry_type ON public.document_registry_record USING btree (registry_type);


--
-- Name: ix_document_registry_record_responsible_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_registry_record_responsible_user_id ON public.document_registry_record USING btree (responsible_user_id);


--
-- Name: ix_document_registry_record_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_document_registry_record_status ON public.document_registry_record USING btree (status);


--
-- Name: ix_drive_item_deleted_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_drive_item_deleted_at ON public.drive_item USING btree (deleted_at);


--
-- Name: ix_drive_item_owner_scope_parent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_drive_item_owner_scope_parent ON public.drive_item USING btree (owner_user_id, scope, parent_id);


--
-- Name: ix_drive_item_owner_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_drive_item_owner_user_id ON public.drive_item USING btree (owner_user_id);


--
-- Name: ix_drive_item_parent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_drive_item_parent_id ON public.drive_item USING btree (parent_id);


--
-- Name: ix_drive_item_scope; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_drive_item_scope ON public.drive_item USING btree (scope);


--
-- Name: ix_drive_item_scope_parent; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_drive_item_scope_parent ON public.drive_item USING btree (scope, parent_id);


--
-- Name: ix_familiarization_author_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_familiarization_author_user_id ON public.familiarization USING btree (author_user_id);


--
-- Name: ix_familiarization_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_familiarization_created_at ON public.familiarization USING btree (created_at);


--
-- Name: ix_familiarization_deadline_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_familiarization_deadline_at ON public.familiarization USING btree (deadline_at);


--
-- Name: ix_familiarization_recipient_acknowledged_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_familiarization_recipient_acknowledged_at ON public.familiarization_recipient USING btree (acknowledged_at);


--
-- Name: ix_familiarization_recipient_familiarization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_familiarization_recipient_familiarization_id ON public.familiarization_recipient USING btree (familiarization_id);


--
-- Name: ix_familiarization_recipient_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_familiarization_recipient_user_id ON public.familiarization_recipient USING btree (user_id);


--
-- Name: ix_familiarization_title; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_familiarization_title ON public.familiarization USING btree (title);


--
-- Name: ix_file_collection_owner_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_collection_owner_user_id ON public.file_collection USING btree (owner_user_id);


--
-- Name: ix_file_collection_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_collection_status ON public.file_collection USING btree (status);


--
-- Name: ix_file_collection_submission_collection_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_collection_submission_collection_id ON public.file_collection_submission USING btree (collection_id);


--
-- Name: ix_file_collection_submission_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_collection_submission_user_id ON public.file_collection_submission USING btree (user_id);


--
-- Name: ix_file_collection_target_collection_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_collection_target_collection_id ON public.file_collection_target USING btree (collection_id);


--
-- Name: ix_file_collection_target_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_file_collection_target_user_id ON public.file_collection_target USING btree (user_id);


--
-- Name: ix_incident_assignee_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_assignee_id ON public.incident USING btree (assignee_id);


--
-- Name: ix_incident_assignee_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_assignee_user ON public.incident_assignee USING btree (user_id);


--
-- Name: ix_incident_assignment_assigned_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_assignment_assigned_at ON public.incident_assignment USING btree (assigned_at);


--
-- Name: ix_incident_assignment_incident_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_assignment_incident_id ON public.incident_assignment USING btree (incident_id);


--
-- Name: ix_incident_author_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_author_id ON public.incident USING btree (author_id);


--
-- Name: ix_incident_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_category ON public.incident USING btree (category);


--
-- Name: ix_incident_child_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_child_child_id ON public.incident_child USING btree (child_id);


--
-- Name: ix_incident_child_incident_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_child_incident_id ON public.incident_child USING btree (incident_id);


--
-- Name: ix_incident_note_attachment_note_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_note_attachment_note_id ON public.incident_note_attachment USING btree (note_id);


--
-- Name: ix_incident_note_author_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_note_author_id ON public.incident_note USING btree (author_id);


--
-- Name: ix_incident_note_incident_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_note_incident_id ON public.incident_note USING btree (incident_id);


--
-- Name: ix_incident_note_parent_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_note_parent_id ON public.incident_note USING btree (parent_id);


--
-- Name: ix_incident_notification_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_notification_created_at ON public.incident_notification USING btree (created_at);


--
-- Name: ix_incident_notification_incident_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_notification_incident_id ON public.incident_notification USING btree (incident_id);


--
-- Name: ix_incident_notification_is_read; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_notification_is_read ON public.incident_notification USING btree (is_read);


--
-- Name: ix_incident_notification_notification_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_notification_notification_type ON public.incident_notification USING btree (notification_type);


--
-- Name: ix_incident_notification_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_notification_user_id ON public.incident_notification USING btree (user_id);


--
-- Name: ix_incident_notification_user_unread; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_notification_user_unread ON public.incident_notification USING btree (user_id, is_read, created_at DESC);


--
-- Name: ix_incident_occurred_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_occurred_at ON public.incident USING btree (occurred_at);


--
-- Name: ix_incident_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_status ON public.incident USING btree (status);


--
-- Name: ix_incident_status_history_changed_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_status_history_changed_at ON public.incident_status_history USING btree (changed_at);


--
-- Name: ix_incident_status_history_incident_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_status_history_incident_id ON public.incident_status_history USING btree (incident_id);


--
-- Name: ix_incident_status_occurred; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_incident_status_occurred ON public.incident USING btree (status, occurred_at DESC);


--
-- Name: ix_iom_card_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_card_academic_year_id ON public.iom_card USING btree (academic_year_id);


--
-- Name: ix_iom_card_agreed_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_card_agreed_by_user_id ON public.iom_card USING btree (agreed_by_user_id);


--
-- Name: ix_iom_card_approved_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_card_approved_by_user_id ON public.iom_card USING btree (approved_by_user_id);


--
-- Name: ix_iom_card_archived_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_card_archived_at ON public.iom_card USING btree (archived_at);


--
-- Name: ix_iom_card_archived_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_card_archived_by_user_id ON public.iom_card USING btree (archived_by_user_id);


--
-- Name: ix_iom_card_building_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_card_building_id ON public.iom_card USING btree (building_id);


--
-- Name: ix_iom_card_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_card_child_id ON public.iom_card USING btree (child_id);


--
-- Name: ix_iom_card_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_card_created_at ON public.iom_card USING btree (created_at);


--
-- Name: ix_iom_card_created_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_card_created_by_user_id ON public.iom_card USING btree (created_by_user_id);


--
-- Name: ix_iom_card_curator_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_card_curator_user_id ON public.iom_card USING btree (curator_user_id);


--
-- Name: ix_iom_card_education_level; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_card_education_level ON public.iom_card USING btree (education_level);


--
-- Name: ix_iom_card_iom_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_card_iom_type ON public.iom_card USING btree (iom_type);


--
-- Name: ix_iom_card_parallel; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_card_parallel ON public.iom_card USING btree (parallel);


--
-- Name: ix_iom_card_previous_card_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_card_previous_card_id ON public.iom_card USING btree (previous_card_id);


--
-- Name: ix_iom_card_school_class_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_card_school_class_id ON public.iom_card USING btree (school_class_id);


--
-- Name: ix_iom_card_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_card_status ON public.iom_card USING btree (status);


--
-- Name: ix_iom_card_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_card_updated_at ON public.iom_card USING btree (updated_at);


--
-- Name: ix_iom_card_updated_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_card_updated_by_user_id ON public.iom_card USING btree (updated_by_user_id);


--
-- Name: ix_iom_cyclegram_link_correction_id; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_iom_cyclegram_link_correction_id ON public.iom_cyclegram_link USING btree (correction_id);


--
-- Name: ix_iom_cyclegram_link_cyclegram_entry_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_cyclegram_link_cyclegram_entry_id ON public.iom_cyclegram_link USING btree (cyclegram_entry_id);


--
-- Name: ix_iom_cyclegram_link_sync_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_cyclegram_link_sync_key ON public.iom_cyclegram_link USING btree (sync_key);


--
-- Name: ix_iom_cyclegram_link_synced_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_cyclegram_link_synced_at ON public.iom_cyclegram_link USING btree (synced_at);


--
-- Name: ix_iom_cyclegram_link_synced_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_cyclegram_link_synced_by_user_id ON public.iom_cyclegram_link USING btree (synced_by_user_id);


--
-- Name: ix_iom_export_log_export_format; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_export_log_export_format ON public.iom_export_log USING btree (export_format);


--
-- Name: ix_iom_export_log_exported_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_export_log_exported_at ON public.iom_export_log USING btree (exported_at);


--
-- Name: ix_iom_export_log_exported_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_export_log_exported_by_user_id ON public.iom_export_log USING btree (exported_by_user_id);


--
-- Name: ix_iom_export_log_iom_card_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_export_log_iom_card_id ON public.iom_export_log USING btree (iom_card_id);


--
-- Name: ix_iom_history_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_history_action ON public.iom_history USING btree (action);


--
-- Name: ix_iom_history_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_history_created_at ON public.iom_history USING btree (created_at);


--
-- Name: ix_iom_history_created_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_history_created_by_user_id ON public.iom_history USING btree (created_by_user_id);


--
-- Name: ix_iom_history_iom_card_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_history_iom_card_id ON public.iom_history USING btree (iom_card_id);


--
-- Name: ix_iom_import_session_schedule_imported_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_import_session_schedule_imported_at ON public.iom_import_session_schedule USING btree (imported_at);


--
-- Name: ix_iom_import_session_schedule_imported_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_import_session_schedule_imported_by_user_id ON public.iom_import_session_schedule USING btree (imported_by_user_id);


--
-- Name: ix_iom_import_session_schedule_iom_card_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_import_session_schedule_iom_card_id ON public.iom_import_session_schedule USING btree (iom_card_id);


--
-- Name: ix_iom_monitoring_entry_block_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_monitoring_entry_block_code ON public.iom_monitoring_entry USING btree (block_code);


--
-- Name: ix_iom_monitoring_entry_iom_card_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_monitoring_entry_iom_card_id ON public.iom_monitoring_entry USING btree (iom_card_id);


--
-- Name: ix_iom_monitoring_entry_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_monitoring_entry_period ON public.iom_monitoring_entry USING btree (period);


--
-- Name: ix_iom_monitoring_entry_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_monitoring_entry_updated_at ON public.iom_monitoring_entry USING btree (updated_at);


--
-- Name: ix_iom_monitoring_entry_updated_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_monitoring_entry_updated_by_user_id ON public.iom_monitoring_entry USING btree (updated_by_user_id);


--
-- Name: ix_iom_monitoring_template_block_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_monitoring_template_block_code ON public.iom_monitoring_template USING btree (block_code);


--
-- Name: ix_iom_monitoring_template_iom_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_monitoring_template_iom_type ON public.iom_monitoring_template USING btree (iom_type);


--
-- Name: ix_iom_monitoring_template_is_enabled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_monitoring_template_is_enabled ON public.iom_monitoring_template USING btree (is_enabled);


--
-- Name: ix_iom_monitoring_template_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_monitoring_template_period ON public.iom_monitoring_template USING btree (period);


--
-- Name: ix_iom_schedule_correction_created_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_schedule_correction_created_by_user_id ON public.iom_schedule_correction USING btree (created_by_user_id);


--
-- Name: ix_iom_schedule_correction_iom_card_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_schedule_correction_iom_card_id ON public.iom_schedule_correction USING btree (iom_card_id);


--
-- Name: ix_iom_schedule_correction_specialist_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_schedule_correction_specialist_id ON public.iom_schedule_correction USING btree (specialist_id);


--
-- Name: ix_iom_schedule_correction_updated_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_schedule_correction_updated_by_user_id ON public.iom_schedule_correction USING btree (updated_by_user_id);


--
-- Name: ix_iom_schedule_correction_weekday; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_schedule_correction_weekday ON public.iom_schedule_correction USING btree (weekday);


--
-- Name: ix_iom_schedule_lesson_iom_card_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_schedule_lesson_iom_card_id ON public.iom_schedule_lesson USING btree (iom_card_id);


--
-- Name: ix_iom_schedule_lesson_source_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_schedule_lesson_source_type ON public.iom_schedule_lesson USING btree (source_type);


--
-- Name: ix_iom_schedule_lesson_weekday; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_schedule_lesson_weekday ON public.iom_schedule_lesson USING btree (weekday);


--
-- Name: ix_iom_section_data_created_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_section_data_created_by_user_id ON public.iom_section_data USING btree (created_by_user_id);


--
-- Name: ix_iom_section_data_iom_card_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_section_data_iom_card_id ON public.iom_section_data USING btree (iom_card_id);


--
-- Name: ix_iom_section_data_section_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_section_data_section_code ON public.iom_section_data USING btree (section_code);


--
-- Name: ix_iom_section_data_updated_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_section_data_updated_by_user_id ON public.iom_section_data USING btree (updated_by_user_id);


--
-- Name: ix_iom_specialist_plan_assignment_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_specialist_plan_assignment_id ON public.iom_specialist_plan USING btree (assignment_id);


--
-- Name: ix_iom_specialist_plan_created_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_specialist_plan_created_by_user_id ON public.iom_specialist_plan USING btree (created_by_user_id);


--
-- Name: ix_iom_specialist_plan_iom_card_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_specialist_plan_iom_card_id ON public.iom_specialist_plan USING btree (iom_card_id);


--
-- Name: ix_iom_specialist_plan_role_title; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_specialist_plan_role_title ON public.iom_specialist_plan USING btree (role_title);


--
-- Name: ix_iom_specialist_plan_specialist_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_specialist_plan_specialist_id ON public.iom_specialist_plan USING btree (specialist_id);


--
-- Name: ix_iom_specialist_plan_updated_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_iom_specialist_plan_updated_by_user_id ON public.iom_specialist_plan USING btree (updated_by_user_id);


--
-- Name: ix_mail_settings_log_action_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mail_settings_log_action_type ON public.mail_settings_log USING btree (action_type);


--
-- Name: ix_mail_settings_log_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mail_settings_log_created_at ON public.mail_settings_log USING btree (created_at);


--
-- Name: ix_mail_settings_log_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mail_settings_log_status ON public.mail_settings_log USING btree (status);


--
-- Name: ix_max_binding_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_max_binding_code ON public.max_binding USING btree (code);


--
-- Name: ix_max_binding_max_chat_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_max_binding_max_chat_id ON public.max_binding USING btree (max_chat_id);


--
-- Name: ix_max_binding_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_max_binding_status ON public.max_binding USING btree (status);


--
-- Name: ix_max_binding_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_max_binding_user_id ON public.max_binding USING btree (user_id);


--
-- Name: ix_max_binding_user_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_max_binding_user_status ON public.max_binding USING btree (user_id, status);


--
-- Name: ix_mobile_push_token_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mobile_push_token_is_active ON public.mobile_push_token USING btree (is_active);


--
-- Name: ix_mobile_push_token_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mobile_push_token_user_id ON public.mobile_push_token USING btree (user_id);


--
-- Name: ix_olympiad_import_session_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_import_session_academic_year_id ON public.olympiad_import_session USING btree (academic_year_id);


--
-- Name: ix_olympiad_import_session_department_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_import_session_department_id ON public.olympiad_import_session USING btree (department_id);


--
-- Name: ix_olympiad_import_session_imported_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_import_session_imported_by ON public.olympiad_import_session USING btree (imported_by);


--
-- Name: ix_olympiad_import_session_stage; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_import_session_stage ON public.olympiad_import_session USING btree (stage);


--
-- Name: ix_olympiad_import_session_subject_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_import_session_subject_id ON public.olympiad_import_session USING btree (subject_id);


--
-- Name: ix_olympiad_result_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_result_academic_year_id ON public.olympiad_result USING btree (academic_year_id);


--
-- Name: ix_olympiad_result_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_result_child_id ON public.olympiad_result USING btree (child_id);


--
-- Name: ix_olympiad_result_department_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_result_department_id ON public.olympiad_result USING btree (department_id);


--
-- Name: ix_olympiad_result_import_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_result_import_session_id ON public.olympiad_result USING btree (import_session_id);


--
-- Name: ix_olympiad_result_is_annulled; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_result_is_annulled ON public.olympiad_result USING btree (is_annulled);


--
-- Name: ix_olympiad_result_school_class_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_result_school_class_id ON public.olympiad_result USING btree (school_class_id);


--
-- Name: ix_olympiad_result_school_ekis; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_result_school_ekis ON public.olympiad_result USING btree (school_ekis);


--
-- Name: ix_olympiad_result_school_login; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_result_school_login ON public.olympiad_result USING btree (school_login);


--
-- Name: ix_olympiad_result_source_row_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_result_source_row_hash ON public.olympiad_result USING btree (source_row_hash);


--
-- Name: ix_olympiad_result_stage; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_result_stage ON public.olympiad_result USING btree (stage);


--
-- Name: ix_olympiad_result_stage_group; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_result_stage_group ON public.olympiad_result USING btree (stage_group);


--
-- Name: ix_olympiad_result_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_result_status ON public.olympiad_result USING btree (status);


--
-- Name: ix_olympiad_result_status_group; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_result_status_group ON public.olympiad_result USING btree (status_group);


--
-- Name: ix_olympiad_result_subject_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_result_subject_id ON public.olympiad_result USING btree (subject_id);


--
-- Name: ix_olympiad_result_teacher_binding_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_result_teacher_binding_source ON public.olympiad_result USING btree (teacher_binding_source);


--
-- Name: ix_olympiad_result_teacher_binding_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_result_teacher_binding_status ON public.olympiad_result USING btree (teacher_binding_status);


--
-- Name: ix_olympiad_result_teacher_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_result_teacher_id ON public.olympiad_result USING btree (teacher_id);


--
-- Name: ix_olympiad_stage_mapping_system_stage_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_stage_mapping_system_stage_code ON public.olympiad_stage_mapping USING btree (system_stage_code);


--
-- Name: ix_olympiad_subject_mapping_department_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_subject_mapping_department_id ON public.olympiad_subject_mapping USING btree (department_id);


--
-- Name: ix_olympiad_subject_mapping_olympiad_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_subject_mapping_olympiad_name ON public.olympiad_subject_mapping USING btree (olympiad_name);


--
-- Name: ix_olympiad_subject_mapping_olympiad_subject_name; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_subject_mapping_olympiad_subject_name ON public.olympiad_subject_mapping USING btree (olympiad_subject_name);


--
-- Name: ix_olympiad_subject_mapping_subject_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_subject_mapping_subject_id ON public.olympiad_subject_mapping USING btree (subject_id);


--
-- Name: ix_olympiad_unmatched_row_import_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_unmatched_row_import_session_id ON public.olympiad_unmatched_row USING btree (import_session_id);


--
-- Name: ix_olympiad_unmatched_row_resolved_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_unmatched_row_resolved_child_id ON public.olympiad_unmatched_row USING btree (resolved_child_id);


--
-- Name: ix_olympiad_unmatched_row_resolved_department_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_unmatched_row_resolved_department_id ON public.olympiad_unmatched_row USING btree (resolved_department_id);


--
-- Name: ix_olympiad_unmatched_row_resolved_teacher_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_olympiad_unmatched_row_resolved_teacher_id ON public.olympiad_unmatched_row USING btree (resolved_teacher_id);


--
-- Name: ix_order_responsible_link_order_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_responsible_link_order_id ON public.order_responsible_link USING btree (order_id);


--
-- Name: ix_order_responsible_link_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_order_responsible_link_user_id ON public.order_responsible_link USING btree (user_id);


--
-- Name: ix_organization_settings_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_organization_settings_is_active ON public.organization_settings USING btree (is_active);


--
-- Name: ix_page_visit_endpoint_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_page_visit_endpoint_ts ON public.page_visit USING btree (endpoint, ts);


--
-- Name: ix_page_visit_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_page_visit_ts ON public.page_visit USING btree (ts);


--
-- Name: ix_page_visit_user_ts; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_page_visit_user_ts ON public.page_visit USING btree (user_id, ts);


--
-- Name: ix_password_reset_token_token_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_password_reset_token_token_hash ON public.password_reset_token USING btree (token_hash);


--
-- Name: ix_password_reset_token_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_password_reset_token_user_id ON public.password_reset_token USING btree (user_id);


--
-- Name: ix_preschool_attendance_record_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_preschool_attendance_record_child_id ON public.preschool_attendance_record USING btree (child_id);


--
-- Name: ix_preschool_attendance_record_group_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_preschool_attendance_record_group_id ON public.preschool_attendance_record USING btree (group_id);


--
-- Name: ix_preschool_attendance_record_upload_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_preschool_attendance_record_upload_id ON public.preschool_attendance_record USING btree (upload_id);


--
-- Name: ix_preschool_attendance_upload_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_preschool_attendance_upload_academic_year_id ON public.preschool_attendance_upload USING btree (academic_year_id);


--
-- Name: ix_preschool_attendance_upload_month; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_preschool_attendance_upload_month ON public.preschool_attendance_upload USING btree (month);


--
-- Name: ix_preschool_child_import_batch_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_preschool_child_import_batch_id ON public.preschool_child USING btree (import_batch_id);


--
-- Name: ix_preschool_child_movement_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_preschool_child_movement_child_id ON public.preschool_child_movement USING btree (child_id);


--
-- Name: ix_preschool_child_movement_from_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_preschool_child_movement_from_academic_year_id ON public.preschool_child_movement USING btree (from_academic_year_id);


--
-- Name: ix_preschool_child_movement_from_group_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_preschool_child_movement_from_group_id ON public.preschool_child_movement USING btree (from_group_id);


--
-- Name: ix_preschool_child_movement_movement_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_preschool_child_movement_movement_date ON public.preschool_child_movement USING btree (movement_date);


--
-- Name: ix_preschool_child_movement_to_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_preschool_child_movement_to_academic_year_id ON public.preschool_child_movement USING btree (to_academic_year_id);


--
-- Name: ix_preschool_child_movement_to_group_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_preschool_child_movement_to_group_id ON public.preschool_child_movement USING btree (to_group_id);


--
-- Name: ix_preschool_children_import_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_preschool_children_import_academic_year_id ON public.preschool_children_import USING btree (academic_year_id);


--
-- Name: ix_preschool_group_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_preschool_group_academic_year_id ON public.preschool_group USING btree (academic_year_id);


--
-- Name: ix_preschool_group_building_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_preschool_group_building_id ON public.preschool_group USING btree (building_id);


--
-- Name: ix_preschool_group_teacher_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_preschool_group_teacher_user_id ON public.preschool_group USING btree (teacher_user_id);


--
-- Name: ix_preschool_representative_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_preschool_representative_child_id ON public.preschool_representative USING btree (child_id);


--
-- Name: ix_role_dashboard_block_block_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_dashboard_block_block_code ON public.role_dashboard_block USING btree (block_code);


--
-- Name: ix_role_dashboard_block_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_dashboard_block_is_active ON public.role_dashboard_block USING btree (is_active);


--
-- Name: ix_role_dashboard_block_role_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_dashboard_block_role_code ON public.role_dashboard_block USING btree (role_code);


--
-- Name: ix_role_module_access_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_module_access_is_active ON public.role_module_access USING btree (is_active);


--
-- Name: ix_role_module_access_module_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_module_access_module_code ON public.role_module_access USING btree (module_code);


--
-- Name: ix_role_module_access_role_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_module_access_role_code ON public.role_module_access USING btree (role_code);


--
-- Name: ix_role_quick_link_access_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_quick_link_access_is_active ON public.role_quick_link_access USING btree (is_active);


--
-- Name: ix_role_quick_link_access_quick_link_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_quick_link_access_quick_link_code ON public.role_quick_link_access USING btree (quick_link_code);


--
-- Name: ix_role_quick_link_access_role_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_role_quick_link_access_role_code ON public.role_quick_link_access USING btree (role_code);


--
-- Name: ix_saved_view_scope; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_saved_view_scope ON public.saved_view USING btree (scope);


--
-- Name: ix_saved_view_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_saved_view_user_id ON public.saved_view USING btree (user_id);


--
-- Name: ix_saved_view_user_scope; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_saved_view_user_scope ON public.saved_view USING btree (user_id, scope);


--
-- Name: ix_school_class_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_class_academic_year_id ON public.school_class USING btree (academic_year_id);


--
-- Name: ix_school_class_building_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_class_building_id ON public.school_class USING btree (building_id);


--
-- Name: ix_school_class_grade_building; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_class_grade_building ON public.school_class USING btree (grade, building_id);


--
-- Name: ix_school_class_teacher_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_class_teacher_user_id ON public.school_class USING btree (teacher_user_id);


--
-- Name: ix_school_class_year_archived; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_class_year_archived ON public.school_class USING btree (academic_year_id, is_archived);


--
-- Name: ix_school_order_number; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_order_number ON public.school_order USING btree (number);


--
-- Name: ix_school_order_section; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_order_section ON public.school_order USING btree (section);


--
-- Name: ix_school_plan_event_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_plan_event_academic_year_id ON public.school_plan_event USING btree (academic_year_id);


--
-- Name: ix_school_plan_event_building_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_plan_event_building_id ON public.school_plan_event USING btree (building_id);


--
-- Name: ix_school_plan_event_category_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_plan_event_category_id ON public.school_plan_event USING btree (category_id);


--
-- Name: ix_school_plan_event_class_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_plan_event_class_id ON public.school_plan_event USING btree (class_id);


--
-- Name: ix_school_plan_event_direction_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_plan_event_direction_id ON public.school_plan_event USING btree (direction_id);


--
-- Name: ix_school_plan_event_end_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_plan_event_end_date ON public.school_plan_event USING btree (end_date);


--
-- Name: ix_school_plan_event_is_archived; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_plan_event_is_archived ON public.school_plan_event USING btree (is_archived);


--
-- Name: ix_school_plan_event_priority; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_plan_event_priority ON public.school_plan_event USING btree (priority);


--
-- Name: ix_school_plan_event_responsible_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_plan_event_responsible_user_id ON public.school_plan_event USING btree (responsible_user_id);


--
-- Name: ix_school_plan_event_start_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_plan_event_start_date ON public.school_plan_event USING btree (start_date);


--
-- Name: ix_school_plan_event_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_plan_event_status ON public.school_plan_event USING btree (status);


--
-- Name: ix_school_plan_event_visibility_level; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_school_plan_event_visibility_level ON public.school_plan_event USING btree (visibility_level);


--
-- Name: ix_service_activity_type_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_service_activity_type_code ON public.service_activity_type USING btree (code);


--
-- Name: ix_service_activity_type_work_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_activity_type_work_category ON public.service_activity_type USING btree (work_category);


--
-- Name: ix_service_assignment_building_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_assignment_building_id ON public.service_assignment USING btree (building_id);


--
-- Name: ix_service_assignment_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_assignment_child_id ON public.service_assignment USING btree (child_id);


--
-- Name: ix_service_assignment_created_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_assignment_created_by_user_id ON public.service_assignment USING btree (created_by_user_id);


--
-- Name: ix_service_assignment_end_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_assignment_end_date ON public.service_assignment USING btree (end_date);


--
-- Name: ix_service_assignment_history_assignment_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_assignment_history_assignment_id ON public.service_assignment_history USING btree (assignment_id);


--
-- Name: ix_service_assignment_history_changed_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_assignment_history_changed_by_user_id ON public.service_assignment_history USING btree (changed_by_user_id);


--
-- Name: ix_service_assignment_history_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_assignment_history_created_at ON public.service_assignment_history USING btree (created_at);


--
-- Name: ix_service_assignment_incident_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_assignment_incident_id ON public.service_assignment USING btree (incident_id);


--
-- Name: ix_service_assignment_specialist_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_assignment_specialist_id ON public.service_assignment USING btree (specialist_id);


--
-- Name: ix_service_assignment_start_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_assignment_start_date ON public.service_assignment USING btree (start_date);


--
-- Name: ix_service_assignment_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_assignment_status ON public.service_assignment USING btree (status);


--
-- Name: ix_service_cyclegram_academic_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_cyclegram_academic_year ON public.service_cyclegram USING btree (academic_year);


--
-- Name: ix_service_cyclegram_entry_activity_type_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_cyclegram_entry_activity_type_id ON public.service_cyclegram_entry USING btree (activity_type_id);


--
-- Name: ix_service_cyclegram_entry_building_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_cyclegram_entry_building_id ON public.service_cyclegram_entry USING btree (building_id);


--
-- Name: ix_service_cyclegram_entry_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_cyclegram_entry_child_id ON public.service_cyclegram_entry USING btree (child_id);


--
-- Name: ix_service_cyclegram_entry_cyclegram_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_cyclegram_entry_cyclegram_id ON public.service_cyclegram_entry USING btree (cyclegram_id);


--
-- Name: ix_service_cyclegram_entry_weekday; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_cyclegram_entry_weekday ON public.service_cyclegram_entry USING btree (weekday);


--
-- Name: ix_service_cyclegram_entry_work_category; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_cyclegram_entry_work_category ON public.service_cyclegram_entry USING btree (work_category);


--
-- Name: ix_service_cyclegram_history_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_cyclegram_history_created_at ON public.service_cyclegram_history USING btree (created_at);


--
-- Name: ix_service_cyclegram_history_cyclegram_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_cyclegram_history_cyclegram_id ON public.service_cyclegram_history USING btree (cyclegram_id);


--
-- Name: ix_service_cyclegram_specialist_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_cyclegram_specialist_id ON public.service_cyclegram USING btree (specialist_id);


--
-- Name: ix_service_cyclegram_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_cyclegram_status ON public.service_cyclegram USING btree (status);


--
-- Name: ix_service_import_unmatched_staff_imported_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_import_unmatched_staff_imported_at ON public.service_import_unmatched_staff USING btree (imported_at);


--
-- Name: ix_service_import_unmatched_staff_matched_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_import_unmatched_staff_matched_user_id ON public.service_import_unmatched_staff USING btree (matched_user_id);


--
-- Name: ix_service_import_unmatched_staff_normalized_fio; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_import_unmatched_staff_normalized_fio ON public.service_import_unmatched_staff USING btree (normalized_fio);


--
-- Name: ix_service_import_unmatched_staff_source; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_import_unmatched_staff_source ON public.service_import_unmatched_staff USING btree (source);


--
-- Name: ix_service_import_unmatched_staff_source_session_key; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_import_unmatched_staff_source_session_key ON public.service_import_unmatched_staff USING btree (source_session_key);


--
-- Name: ix_service_import_unmatched_staff_staff_fio; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_import_unmatched_staff_staff_fio ON public.service_import_unmatched_staff USING btree (staff_fio);


--
-- Name: ix_service_import_unmatched_staff_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_import_unmatched_staff_status ON public.service_import_unmatched_staff USING btree (status);


--
-- Name: ix_service_presentation_academic_year; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_presentation_academic_year ON public.service_presentation USING btree (academic_year);


--
-- Name: ix_service_presentation_basis; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_presentation_basis ON public.service_presentation USING btree (basis);


--
-- Name: ix_service_presentation_block_block_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_presentation_block_block_code ON public.service_presentation_block USING btree (block_code);


--
-- Name: ix_service_presentation_block_executor_specialist_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_presentation_block_executor_specialist_id ON public.service_presentation_block USING btree (executor_specialist_id);


--
-- Name: ix_service_presentation_block_executor_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_presentation_block_executor_user_id ON public.service_presentation_block USING btree (executor_user_id);


--
-- Name: ix_service_presentation_block_presentation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_presentation_block_presentation_id ON public.service_presentation_block USING btree (presentation_id);


--
-- Name: ix_service_presentation_block_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_presentation_block_status ON public.service_presentation_block USING btree (status);


--
-- Name: ix_service_presentation_building_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_presentation_building_id ON public.service_presentation USING btree (building_id);


--
-- Name: ix_service_presentation_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_presentation_child_id ON public.service_presentation USING btree (child_id);


--
-- Name: ix_service_presentation_history_block_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_presentation_history_block_id ON public.service_presentation_history USING btree (block_id);


--
-- Name: ix_service_presentation_history_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_presentation_history_created_at ON public.service_presentation_history USING btree (created_at);


--
-- Name: ix_service_presentation_history_presentation_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_presentation_history_presentation_id ON public.service_presentation_history USING btree (presentation_id);


--
-- Name: ix_service_presentation_history_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_presentation_history_user_id ON public.service_presentation_history USING btree (user_id);


--
-- Name: ix_service_presentation_methodist_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_presentation_methodist_user_id ON public.service_presentation USING btree (methodist_user_id);


--
-- Name: ix_service_presentation_school_class_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_presentation_school_class_id ON public.service_presentation USING btree (school_class_id);


--
-- Name: ix_service_presentation_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_presentation_status ON public.service_presentation USING btree (status);


--
-- Name: ix_service_rate_norm_building_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_rate_norm_building_id ON public.service_rate_norm USING btree (building_id);


--
-- Name: ix_service_rate_norm_effective_from; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_rate_norm_effective_from ON public.service_rate_norm USING btree (effective_from);


--
-- Name: ix_service_rate_norm_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_rate_norm_is_active ON public.service_rate_norm USING btree (is_active);


--
-- Name: ix_service_rate_norm_specialization_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_rate_norm_specialization_id ON public.service_rate_norm USING btree (specialization_id);


--
-- Name: ix_service_responsible_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_responsible_is_active ON public.service_responsible USING btree (is_active);


--
-- Name: ix_service_responsible_specialist_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_responsible_specialist_id ON public.service_responsible USING btree (specialist_id);


--
-- Name: ix_service_specialist_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_specialist_is_active ON public.service_specialist USING btree (is_active);


--
-- Name: ix_service_specialist_main_building_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_specialist_main_building_id ON public.service_specialist USING btree (main_building_id);


--
-- Name: ix_service_specialist_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_service_specialist_user_id ON public.service_specialist USING btree (user_id);


--
-- Name: ix_service_specialization_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_service_specialization_code ON public.service_specialization USING btree (code);


--
-- Name: ix_support_case_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_support_case_academic_year_id ON public.support_case USING btree (academic_year_id);


--
-- Name: ix_support_case_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_support_case_child_id ON public.support_case USING btree (child_id);


--
-- Name: ix_support_case_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_support_case_status ON public.support_case USING btree (status);


--
-- Name: ix_support_case_support_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_support_case_support_type ON public.support_case USING btree (support_type);


--
-- Name: ix_system_log_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_system_log_action ON public.system_log USING btree (action);


--
-- Name: ix_system_log_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_system_log_created_at ON public.system_log USING btree (created_at);


--
-- Name: ix_system_log_object_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_system_log_object_id ON public.system_log USING btree (object_id);


--
-- Name: ix_system_log_object_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_system_log_object_type ON public.system_log USING btree (object_type);


--
-- Name: ix_system_log_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_system_log_user_id ON public.system_log USING btree (user_id);


--
-- Name: ix_system_mail_settings_is_active; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_system_mail_settings_is_active ON public.system_mail_settings USING btree (is_active);


--
-- Name: ix_task_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_academic_year_id ON public.task USING btree (academic_year_id);


--
-- Name: ix_task_attachment_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_attachment_created_at ON public.task_attachment USING btree (created_at);


--
-- Name: ix_task_attachment_file_kind; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_attachment_file_kind ON public.task_attachment USING btree (file_kind);


--
-- Name: ix_task_attachment_is_deleted; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_attachment_is_deleted ON public.task_attachment USING btree (is_deleted);


--
-- Name: ix_task_attachment_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_attachment_task_id ON public.task_attachment USING btree (task_id);


--
-- Name: ix_task_attachment_uploaded_by_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_attachment_uploaded_by_user_id ON public.task_attachment USING btree (uploaded_by_user_id);


--
-- Name: ix_task_checklist_item_is_done; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_checklist_item_is_done ON public.task_checklist_item USING btree (is_done);


--
-- Name: ix_task_checklist_item_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_checklist_item_task_id ON public.task_checklist_item USING btree (task_id);


--
-- Name: ix_task_child_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_child_id ON public.task USING btree (child_id);


--
-- Name: ix_task_class_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_class_id ON public.task USING btree (class_id);


--
-- Name: ix_task_comment_author_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_comment_author_user_id ON public.task_comment USING btree (author_user_id);


--
-- Name: ix_task_comment_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_comment_task_id ON public.task_comment USING btree (task_id);


--
-- Name: ix_task_controller_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_controller_user_id ON public.task USING btree (controller_user_id);


--
-- Name: ix_task_creator_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_creator_user_id ON public.task USING btree (creator_user_id);


--
-- Name: ix_task_deadline_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_deadline_at ON public.task USING btree (deadline_at);


--
-- Name: ix_task_email_log_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_email_log_created_at ON public.task_email_log USING btree (created_at);


--
-- Name: ix_task_email_log_notification_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_email_log_notification_type ON public.task_email_log USING btree (notification_type);


--
-- Name: ix_task_email_log_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_email_log_status ON public.task_email_log USING btree (status);


--
-- Name: ix_task_email_log_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_email_log_task_id ON public.task_email_log USING btree (task_id);


--
-- Name: ix_task_email_log_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_email_log_user_id ON public.task_email_log USING btree (user_id);


--
-- Name: ix_task_history_actor_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_history_actor_user_id ON public.task_history USING btree (actor_user_id);


--
-- Name: ix_task_history_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_history_created_at ON public.task_history USING btree (created_at);


--
-- Name: ix_task_history_event_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_history_event_type ON public.task_history USING btree (event_type);


--
-- Name: ix_task_history_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_history_task_id ON public.task_history USING btree (task_id);


--
-- Name: ix_task_incident_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_incident_id ON public.task USING btree (incident_id);


--
-- Name: ix_task_notification_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_notification_created_at ON public.task_notification USING btree (created_at);


--
-- Name: ix_task_notification_is_important; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_notification_is_important ON public.task_notification USING btree (is_important);


--
-- Name: ix_task_notification_is_read; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_notification_is_read ON public.task_notification USING btree (is_read);


--
-- Name: ix_task_notification_notification_type; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_notification_notification_type ON public.task_notification USING btree (notification_type);


--
-- Name: ix_task_notification_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_notification_task_id ON public.task_notification USING btree (task_id);


--
-- Name: ix_task_notification_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_notification_user_id ON public.task_notification USING btree (user_id);


--
-- Name: ix_task_notification_user_unread; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_notification_user_unread ON public.task_notification USING btree (user_id, is_read, created_at DESC);


--
-- Name: ix_task_parent_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_parent_task_id ON public.task USING btree (parent_task_id);


--
-- Name: ix_task_participant_role; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_participant_role ON public.task_participant USING btree (role);


--
-- Name: ix_task_participant_task_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_participant_task_id ON public.task_participant USING btree (task_id);


--
-- Name: ix_task_participant_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_participant_user_id ON public.task_participant USING btree (user_id);


--
-- Name: ix_task_priority; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_priority ON public.task USING btree (priority);


--
-- Name: ix_task_responsible_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_responsible_status ON public.task USING btree (responsible_user_id, status);


--
-- Name: ix_task_responsible_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_responsible_user_id ON public.task USING btree (responsible_user_id);


--
-- Name: ix_task_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_status ON public.task USING btree (status);


--
-- Name: ix_task_status_deadline; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_status_deadline ON public.task USING btree (status, deadline_at);


--
-- Name: ix_task_task_type_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_task_type_id ON public.task USING btree (task_type_id);


--
-- Name: ix_task_template_checklist_item_template_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_template_checklist_item_template_id ON public.task_template_checklist_item USING btree (template_id);


--
-- Name: ix_task_template_task_type_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_task_template_task_type_id ON public.task_template USING btree (task_type_id);


--
-- Name: ix_teacher_course_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_teacher_course_academic_year_id ON public.teacher_course USING btree (academic_year_id);


--
-- Name: ix_teacher_course_teacher_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_teacher_course_teacher_id ON public.teacher_course USING btree (teacher_id);


--
-- Name: ix_teacher_load_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_teacher_load_academic_year_id ON public.teacher_load USING btree (academic_year_id);


--
-- Name: ix_teacher_load_building_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_teacher_load_building_id ON public.teacher_load USING btree (building_id);


--
-- Name: ix_teacher_load_department_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_teacher_load_department_id ON public.teacher_load USING btree (department_id);


--
-- Name: ix_teacher_load_subject_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_teacher_load_subject_id ON public.teacher_load USING btree (subject_id);


--
-- Name: ix_teacher_load_teacher_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_teacher_load_teacher_id ON public.teacher_load USING btree (teacher_id);


--
-- Name: ix_teacher_mcko_result_academic_year_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_teacher_mcko_result_academic_year_id ON public.teacher_mcko_result USING btree (academic_year_id);


--
-- Name: ix_teacher_mcko_result_subject_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_teacher_mcko_result_subject_id ON public.teacher_mcko_result USING btree (subject_id);


--
-- Name: ix_teacher_mcko_result_teacher_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_teacher_mcko_result_teacher_id ON public.teacher_mcko_result USING btree (teacher_id);


--
-- Name: ix_user_building_building_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_building_building_id ON public.user_building USING btree (building_id);


--
-- Name: ix_user_building_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_building_user_id ON public.user_building USING btree (user_id);


--
-- Name: ix_user_employment_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_employment_status ON public."user" USING btree (employment_status);


--
-- Name: ix_user_import_row_action; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_import_row_action ON public.user_import_row USING btree (action);


--
-- Name: ix_user_import_row_session_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_import_row_session_id ON public.user_import_row USING btree (session_id);


--
-- Name: ix_user_import_row_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_import_row_user_id ON public.user_import_row USING btree (user_id);


--
-- Name: ix_user_import_row_username; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_import_row_username ON public.user_import_row USING btree (username);


--
-- Name: ix_user_import_session_imported_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_import_session_imported_at ON public.user_import_session USING btree (imported_at);


--
-- Name: ix_user_import_session_imported_by; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_import_session_imported_by ON public.user_import_session USING btree (imported_by);


--
-- Name: ix_user_import_session_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_user_import_session_status ON public.user_import_session USING btree (status);


--
-- Name: appeal_attachment appeal_attachment_appeal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appeal_attachment
    ADD CONSTRAINT appeal_attachment_appeal_id_fkey FOREIGN KEY (appeal_id) REFERENCES public.appeal(id);


--
-- Name: appeal_attachment appeal_attachment_uploaded_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appeal_attachment
    ADD CONSTRAINT appeal_attachment_uploaded_by_user_id_fkey FOREIGN KEY (uploaded_by_user_id) REFERENCES public."user"(id);


--
-- Name: appeal appeal_creator_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appeal
    ADD CONSTRAINT appeal_creator_user_id_fkey FOREIGN KEY (creator_user_id) REFERENCES public."user"(id);


--
-- Name: appeal appeal_linked_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appeal
    ADD CONSTRAINT appeal_linked_task_id_fkey FOREIGN KEY (linked_task_id) REFERENCES public.task(id);


--
-- Name: appeal appeal_responsible_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.appeal
    ADD CONSTRAINT appeal_responsible_user_id_fkey FOREIGN KEY (responsible_user_id) REFERENCES public."user"(id);


--
-- Name: attendance_import_session attendance_import_session_building_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_import_session
    ADD CONSTRAINT attendance_import_session_building_id_fkey FOREIGN KEY (building_id) REFERENCES public.buildings(id);


--
-- Name: attendance_import_session attendance_import_session_imported_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_import_session
    ADD CONSTRAINT attendance_import_session_imported_by_fkey FOREIGN KEY (imported_by) REFERENCES public."user"(id);


--
-- Name: attendance_late attendance_late_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_late
    ADD CONSTRAINT attendance_late_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: attendance_late attendance_late_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_late
    ADD CONSTRAINT attendance_late_class_id_fkey FOREIGN KEY (class_id) REFERENCES public.school_class(id);


--
-- Name: attendance_late attendance_late_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_late
    ADD CONSTRAINT attendance_late_created_by_fkey FOREIGN KEY (created_by) REFERENCES public."user"(id);


--
-- Name: attendance_late attendance_late_import_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_late
    ADD CONSTRAINT attendance_late_import_session_id_fkey FOREIGN KEY (import_session_id) REFERENCES public.attendance_import_session(id);


--
-- Name: attendance_pass attendance_pass_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_pass
    ADD CONSTRAINT attendance_pass_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: attendance_pass attendance_pass_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_pass
    ADD CONSTRAINT attendance_pass_class_id_fkey FOREIGN KEY (class_id) REFERENCES public.school_class(id);


--
-- Name: attendance_pass attendance_pass_issued_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_pass
    ADD CONSTRAINT attendance_pass_issued_by_fkey FOREIGN KEY (issued_by) REFERENCES public."user"(id);


--
-- Name: attendance_raw_entry attendance_raw_entry_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_raw_entry
    ADD CONSTRAINT attendance_raw_entry_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: attendance_raw_entry attendance_raw_entry_import_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_raw_entry
    ADD CONSTRAINT attendance_raw_entry_import_session_id_fkey FOREIGN KEY (import_session_id) REFERENCES public.attendance_import_session(id);


--
-- Name: attendance_raw_entry attendance_raw_entry_matched_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_raw_entry
    ADD CONSTRAINT attendance_raw_entry_matched_class_id_fkey FOREIGN KEY (matched_class_id) REFERENCES public.school_class(id);


--
-- Name: attendance_schedule_rule attendance_schedule_rule_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_schedule_rule
    ADD CONSTRAINT attendance_schedule_rule_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: attendance_schedule_rule_class attendance_schedule_rule_class_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_schedule_rule_class
    ADD CONSTRAINT attendance_schedule_rule_class_class_id_fkey FOREIGN KEY (class_id) REFERENCES public.school_class(id);


--
-- Name: attendance_schedule_rule_class attendance_schedule_rule_class_rule_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_schedule_rule_class
    ADD CONSTRAINT attendance_schedule_rule_class_rule_id_fkey FOREIGN KEY (rule_id) REFERENCES public.attendance_schedule_rule(id);


--
-- Name: attendance_schedule_rule attendance_schedule_rule_school_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.attendance_schedule_rule
    ADD CONSTRAINT attendance_schedule_rule_school_class_id_fkey FOREIGN KEY (school_class_id) REFERENCES public.school_class(id);


--
-- Name: child_comments child_comments_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_comments
    ADD CONSTRAINT child_comments_author_id_fkey FOREIGN KEY (author_id) REFERENCES public."user"(id);


--
-- Name: child_comments child_comments_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_comments
    ADD CONSTRAINT child_comments_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: child_enrollment child_enrollment_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_enrollment
    ADD CONSTRAINT child_enrollment_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: child_enrollment child_enrollment_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_enrollment
    ADD CONSTRAINT child_enrollment_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: child_enrollment child_enrollment_school_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_enrollment
    ADD CONSTRAINT child_enrollment_school_class_id_fkey FOREIGN KEY (school_class_id) REFERENCES public.school_class(id);


--
-- Name: child_events child_events_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_events
    ADD CONSTRAINT child_events_author_id_fkey FOREIGN KEY (author_id) REFERENCES public."user"(id);


--
-- Name: child_events child_events_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_events
    ADD CONSTRAINT child_events_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: child_movement child_movement_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_movement
    ADD CONSTRAINT child_movement_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: child_movement child_movement_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_movement
    ADD CONSTRAINT child_movement_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: child_movement child_movement_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_movement
    ADD CONSTRAINT child_movement_created_by_fkey FOREIGN KEY (created_by) REFERENCES public."user"(id);


--
-- Name: child_movement child_movement_from_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_movement
    ADD CONSTRAINT child_movement_from_class_id_fkey FOREIGN KEY (from_class_id) REFERENCES public.school_class(id);


--
-- Name: child_movement child_movement_to_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_movement
    ADD CONSTRAINT child_movement_to_class_id_fkey FOREIGN KEY (to_class_id) REFERENCES public.school_class(id);


--
-- Name: child_parent child_parent_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_parent
    ADD CONSTRAINT child_parent_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: child_parent child_parent_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_parent
    ADD CONSTRAINT child_parent_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.parent(id);


--
-- Name: child_social child_social_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_social
    ADD CONSTRAINT child_social_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: child_transfer_history child_transfer_history_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_transfer_history
    ADD CONSTRAINT child_transfer_history_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: child_transfer_history child_transfer_history_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_transfer_history
    ADD CONSTRAINT child_transfer_history_created_by_fkey FOREIGN KEY (created_by) REFERENCES public."user"(id);


--
-- Name: child_transfer_history child_transfer_history_from_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_transfer_history
    ADD CONSTRAINT child_transfer_history_from_academic_year_id_fkey FOREIGN KEY (from_academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: child_transfer_history child_transfer_history_from_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_transfer_history
    ADD CONSTRAINT child_transfer_history_from_class_id_fkey FOREIGN KEY (from_class_id) REFERENCES public.school_class(id);


--
-- Name: child_transfer_history child_transfer_history_to_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_transfer_history
    ADD CONSTRAINT child_transfer_history_to_academic_year_id_fkey FOREIGN KEY (to_academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: child_transfer_history child_transfer_history_to_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.child_transfer_history
    ADD CONSTRAINT child_transfer_history_to_class_id_fkey FOREIGN KEY (to_class_id) REFERENCES public.school_class(id);


--
-- Name: control_work control_work_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work
    ADD CONSTRAINT control_work_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: control_work_assignment control_work_assignment_control_work_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_assignment
    ADD CONSTRAINT control_work_assignment_control_work_id_fkey FOREIGN KEY (control_work_id) REFERENCES public.control_work(id);


--
-- Name: control_work_assignment control_work_assignment_school_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_assignment
    ADD CONSTRAINT control_work_assignment_school_class_id_fkey FOREIGN KEY (school_class_id) REFERENCES public.school_class(id);


--
-- Name: control_work_assignment control_work_assignment_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_assignment
    ADD CONSTRAINT control_work_assignment_teacher_id_fkey FOREIGN KEY (teacher_id) REFERENCES public."user"(id);


--
-- Name: control_work control_work_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work
    ADD CONSTRAINT control_work_created_by_fkey FOREIGN KEY (created_by) REFERENCES public."user"(id);


--
-- Name: control_work_log control_work_log_control_work_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_log
    ADD CONSTRAINT control_work_log_control_work_id_fkey FOREIGN KEY (control_work_id) REFERENCES public.control_work(id);


--
-- Name: control_work_log control_work_log_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_log
    ADD CONSTRAINT control_work_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: control_work_result control_work_result_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_result
    ADD CONSTRAINT control_work_result_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: control_work_result control_work_result_assignment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_result
    ADD CONSTRAINT control_work_result_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.control_work_assignment(id);


--
-- Name: control_work_result control_work_result_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_result
    ADD CONSTRAINT control_work_result_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: control_work_result control_work_result_control_work_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_result
    ADD CONSTRAINT control_work_result_control_work_id_fkey FOREIGN KEY (control_work_id) REFERENCES public.control_work(id);


--
-- Name: control_work_result control_work_result_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_result
    ADD CONSTRAINT control_work_result_created_by_fkey FOREIGN KEY (created_by) REFERENCES public."user"(id);


--
-- Name: control_work_result control_work_result_school_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_result
    ADD CONSTRAINT control_work_result_school_class_id_fkey FOREIGN KEY (school_class_id) REFERENCES public.school_class(id);


--
-- Name: control_work control_work_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work
    ADD CONSTRAINT control_work_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id);


--
-- Name: control_work_task control_work_task_control_work_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work_task
    ADD CONSTRAINT control_work_task_control_work_id_fkey FOREIGN KEY (control_work_id) REFERENCES public.control_work(id);


--
-- Name: control_work control_work_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.control_work
    ADD CONSTRAINT control_work_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public."user"(id);


--
-- Name: debt debt_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.debt
    ADD CONSTRAINT debt_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: debt debt_closed_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.debt
    ADD CONSTRAINT debt_closed_by_user_id_fkey FOREIGN KEY (closed_by_user_id) REFERENCES public."user"(id);


--
-- Name: debt debt_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.debt
    ADD CONSTRAINT debt_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id);


--
-- Name: department_leader department_leader_building_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.department_leader
    ADD CONSTRAINT department_leader_building_id_fkey FOREIGN KEY (building_id) REFERENCES public.buildings(id);


--
-- Name: department_leader department_leader_department_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.department_leader
    ADD CONSTRAINT department_leader_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.department(id);


--
-- Name: department_leader department_leader_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.department_leader
    ADD CONSTRAINT department_leader_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: department_subject department_subject_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.department_subject
    ADD CONSTRAINT department_subject_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: department_subject department_subject_department_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.department_subject
    ADD CONSTRAINT department_subject_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.department(id);


--
-- Name: department_subject department_subject_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.department_subject
    ADD CONSTRAINT department_subject_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id);


--
-- Name: diagnostic_import_batch diagnostic_import_batch_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_import_batch
    ADD CONSTRAINT diagnostic_import_batch_created_by_fkey FOREIGN KEY (created_by) REFERENCES public."user"(id);


--
-- Name: diagnostic_import_batch diagnostic_import_batch_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_import_batch
    ADD CONSTRAINT diagnostic_import_batch_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.diagnostic_session(id);


--
-- Name: diagnostic_import_issue diagnostic_import_issue_import_batch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_import_issue
    ADD CONSTRAINT diagnostic_import_issue_import_batch_id_fkey FOREIGN KEY (import_batch_id) REFERENCES public.diagnostic_import_batch(id);


--
-- Name: diagnostic_import_issue diagnostic_import_issue_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_import_issue
    ADD CONSTRAINT diagnostic_import_issue_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.diagnostic_session(id);


--
-- Name: diagnostic_kes_result diagnostic_kes_result_import_batch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_kes_result
    ADD CONSTRAINT diagnostic_kes_result_import_batch_id_fkey FOREIGN KEY (import_batch_id) REFERENCES public.diagnostic_import_batch(id);


--
-- Name: diagnostic_kes_result diagnostic_kes_result_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_kes_result
    ADD CONSTRAINT diagnostic_kes_result_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.diagnostic_session(id);


--
-- Name: diagnostic_result diagnostic_result_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_result
    ADD CONSTRAINT diagnostic_result_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: diagnostic_result diagnostic_result_import_batch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_result
    ADD CONSTRAINT diagnostic_result_import_batch_id_fkey FOREIGN KEY (import_batch_id) REFERENCES public.diagnostic_import_batch(id);


--
-- Name: diagnostic_result diagnostic_result_replaced_result_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_result
    ADD CONSTRAINT diagnostic_result_replaced_result_id_fkey FOREIGN KEY (replaced_result_id) REFERENCES public.diagnostic_result(id);


--
-- Name: diagnostic_result diagnostic_result_school_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_result
    ADD CONSTRAINT diagnostic_result_school_class_id_fkey FOREIGN KEY (school_class_id) REFERENCES public.school_class(id);


--
-- Name: diagnostic_result diagnostic_result_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_result
    ADD CONSTRAINT diagnostic_result_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.diagnostic_session(id);


--
-- Name: diagnostic_session diagnostic_session_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_session
    ADD CONSTRAINT diagnostic_session_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: diagnostic_session diagnostic_session_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_session
    ADD CONSTRAINT diagnostic_session_created_by_fkey FOREIGN KEY (created_by) REFERENCES public."user"(id);


--
-- Name: diagnostic_student_code diagnostic_student_code_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_student_code
    ADD CONSTRAINT diagnostic_student_code_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: diagnostic_student_code diagnostic_student_code_school_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_student_code
    ADD CONSTRAINT diagnostic_student_code_school_class_id_fkey FOREIGN KEY (school_class_id) REFERENCES public.school_class(id);


--
-- Name: diagnostic_student_code diagnostic_student_code_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_student_code
    ADD CONSTRAINT diagnostic_student_code_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.diagnostic_session(id);


--
-- Name: diagnostic_task_result diagnostic_task_result_result_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_task_result
    ADD CONSTRAINT diagnostic_task_result_result_id_fkey FOREIGN KEY (result_id) REFERENCES public.diagnostic_result(id);


--
-- Name: diagnostic_teacher_binding diagnostic_teacher_binding_result_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_teacher_binding
    ADD CONSTRAINT diagnostic_teacher_binding_result_id_fkey FOREIGN KEY (result_id) REFERENCES public.diagnostic_result(id);


--
-- Name: diagnostic_teacher_binding diagnostic_teacher_binding_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.diagnostic_teacher_binding
    ADD CONSTRAINT diagnostic_teacher_binding_teacher_id_fkey FOREIGN KEY (teacher_id) REFERENCES public."user"(id);


--
-- Name: document document_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document
    ADD CONSTRAINT document_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: document document_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document
    ADD CONSTRAINT document_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: document document_debt_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document
    ADD CONSTRAINT document_debt_id_fkey FOREIGN KEY (debt_id) REFERENCES public.debt(id);


--
-- Name: document document_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document
    ADD CONSTRAINT document_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public."user"(id);


--
-- Name: document_registry_access document_registry_access_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_registry_access
    ADD CONSTRAINT document_registry_access_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: document_registry_record document_registry_record_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_registry_record
    ADD CONSTRAINT document_registry_record_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public."user"(id);


--
-- Name: document_registry_record document_registry_record_responsible_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_registry_record
    ADD CONSTRAINT document_registry_record_responsible_user_id_fkey FOREIGN KEY (responsible_user_id) REFERENCES public."user"(id);


--
-- Name: document document_uploaded_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document
    ADD CONSTRAINT document_uploaded_by_user_id_fkey FOREIGN KEY (uploaded_by_user_id) REFERENCES public."user"(id);


--
-- Name: drive_item drive_item_owner_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.drive_item
    ADD CONSTRAINT drive_item_owner_user_id_fkey FOREIGN KEY (owner_user_id) REFERENCES public."user"(id);


--
-- Name: drive_item drive_item_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.drive_item
    ADD CONSTRAINT drive_item_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.drive_item(id) ON DELETE CASCADE;


--
-- Name: familiarization familiarization_author_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.familiarization
    ADD CONSTRAINT familiarization_author_user_id_fkey FOREIGN KEY (author_user_id) REFERENCES public."user"(id);


--
-- Name: familiarization_recipient familiarization_recipient_familiarization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.familiarization_recipient
    ADD CONSTRAINT familiarization_recipient_familiarization_id_fkey FOREIGN KEY (familiarization_id) REFERENCES public.familiarization(id);


--
-- Name: familiarization_recipient familiarization_recipient_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.familiarization_recipient
    ADD CONSTRAINT familiarization_recipient_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: file_collection file_collection_owner_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_collection
    ADD CONSTRAINT file_collection_owner_user_id_fkey FOREIGN KEY (owner_user_id) REFERENCES public."user"(id);


--
-- Name: file_collection_submission file_collection_submission_collection_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_collection_submission
    ADD CONSTRAINT file_collection_submission_collection_id_fkey FOREIGN KEY (collection_id) REFERENCES public.file_collection(id) ON DELETE CASCADE;


--
-- Name: file_collection_submission file_collection_submission_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_collection_submission
    ADD CONSTRAINT file_collection_submission_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: file_collection_target file_collection_target_collection_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_collection_target
    ADD CONSTRAINT file_collection_target_collection_id_fkey FOREIGN KEY (collection_id) REFERENCES public.file_collection(id) ON DELETE CASCADE;


--
-- Name: file_collection_target file_collection_target_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_collection_target
    ADD CONSTRAINT file_collection_target_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: incident_assignee incident_assignee_added_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_assignee
    ADD CONSTRAINT incident_assignee_added_by_id_fkey FOREIGN KEY (added_by_id) REFERENCES public."user"(id);


--
-- Name: incident incident_assignee_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident
    ADD CONSTRAINT incident_assignee_id_fkey FOREIGN KEY (assignee_id) REFERENCES public."user"(id);


--
-- Name: incident_assignee incident_assignee_incident_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_assignee
    ADD CONSTRAINT incident_assignee_incident_id_fkey FOREIGN KEY (incident_id) REFERENCES public.incident(id) ON DELETE CASCADE;


--
-- Name: incident_assignee incident_assignee_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_assignee
    ADD CONSTRAINT incident_assignee_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id) ON DELETE CASCADE;


--
-- Name: incident_assignment incident_assignment_assigned_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_assignment
    ADD CONSTRAINT incident_assignment_assigned_by_id_fkey FOREIGN KEY (assigned_by_id) REFERENCES public."user"(id);


--
-- Name: incident_assignment incident_assignment_from_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_assignment
    ADD CONSTRAINT incident_assignment_from_user_id_fkey FOREIGN KEY (from_user_id) REFERENCES public."user"(id);


--
-- Name: incident_assignment incident_assignment_incident_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_assignment
    ADD CONSTRAINT incident_assignment_incident_id_fkey FOREIGN KEY (incident_id) REFERENCES public.incident(id);


--
-- Name: incident_assignment incident_assignment_to_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_assignment
    ADD CONSTRAINT incident_assignment_to_user_id_fkey FOREIGN KEY (to_user_id) REFERENCES public."user"(id);


--
-- Name: incident incident_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident
    ADD CONSTRAINT incident_author_id_fkey FOREIGN KEY (author_id) REFERENCES public."user"(id);


--
-- Name: incident_child incident_child_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_child
    ADD CONSTRAINT incident_child_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: incident_child incident_child_incident_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_child
    ADD CONSTRAINT incident_child_incident_id_fkey FOREIGN KEY (incident_id) REFERENCES public.incident(id);


--
-- Name: incident_note_attachment incident_note_attachment_note_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_note_attachment
    ADD CONSTRAINT incident_note_attachment_note_id_fkey FOREIGN KEY (note_id) REFERENCES public.incident_note(id);


--
-- Name: incident_note_attachment incident_note_attachment_uploaded_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_note_attachment
    ADD CONSTRAINT incident_note_attachment_uploaded_by_user_id_fkey FOREIGN KEY (uploaded_by_user_id) REFERENCES public."user"(id);


--
-- Name: incident_note incident_note_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_note
    ADD CONSTRAINT incident_note_author_id_fkey FOREIGN KEY (author_id) REFERENCES public."user"(id);


--
-- Name: incident_note incident_note_incident_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_note
    ADD CONSTRAINT incident_note_incident_id_fkey FOREIGN KEY (incident_id) REFERENCES public.incident(id);


--
-- Name: incident_note incident_note_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_note
    ADD CONSTRAINT incident_note_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.incident_note(id);


--
-- Name: incident_notification incident_notification_incident_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_notification
    ADD CONSTRAINT incident_notification_incident_id_fkey FOREIGN KEY (incident_id) REFERENCES public.incident(id);


--
-- Name: incident_notification incident_notification_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_notification
    ADD CONSTRAINT incident_notification_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: incident_status_history incident_status_history_changed_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_status_history
    ADD CONSTRAINT incident_status_history_changed_by_id_fkey FOREIGN KEY (changed_by_id) REFERENCES public."user"(id);


--
-- Name: incident_status_history incident_status_history_incident_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.incident_status_history
    ADD CONSTRAINT incident_status_history_incident_id_fkey FOREIGN KEY (incident_id) REFERENCES public.incident(id);


--
-- Name: iom_card iom_card_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_card
    ADD CONSTRAINT iom_card_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: iom_card iom_card_agreed_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_card
    ADD CONSTRAINT iom_card_agreed_by_user_id_fkey FOREIGN KEY (agreed_by_user_id) REFERENCES public."user"(id);


--
-- Name: iom_card iom_card_approved_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_card
    ADD CONSTRAINT iom_card_approved_by_user_id_fkey FOREIGN KEY (approved_by_user_id) REFERENCES public."user"(id);


--
-- Name: iom_card iom_card_archived_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_card
    ADD CONSTRAINT iom_card_archived_by_user_id_fkey FOREIGN KEY (archived_by_user_id) REFERENCES public."user"(id);


--
-- Name: iom_card iom_card_building_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_card
    ADD CONSTRAINT iom_card_building_id_fkey FOREIGN KEY (building_id) REFERENCES public.buildings(id);


--
-- Name: iom_card iom_card_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_card
    ADD CONSTRAINT iom_card_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: iom_card iom_card_created_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_card
    ADD CONSTRAINT iom_card_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public."user"(id);


--
-- Name: iom_card iom_card_curator_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_card
    ADD CONSTRAINT iom_card_curator_user_id_fkey FOREIGN KEY (curator_user_id) REFERENCES public."user"(id);


--
-- Name: iom_card iom_card_previous_card_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_card
    ADD CONSTRAINT iom_card_previous_card_id_fkey FOREIGN KEY (previous_card_id) REFERENCES public.iom_card(id);


--
-- Name: iom_card iom_card_school_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_card
    ADD CONSTRAINT iom_card_school_class_id_fkey FOREIGN KEY (school_class_id) REFERENCES public.school_class(id);


--
-- Name: iom_card iom_card_updated_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_card
    ADD CONSTRAINT iom_card_updated_by_user_id_fkey FOREIGN KEY (updated_by_user_id) REFERENCES public."user"(id);


--
-- Name: iom_cyclegram_link iom_cyclegram_link_correction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_cyclegram_link
    ADD CONSTRAINT iom_cyclegram_link_correction_id_fkey FOREIGN KEY (correction_id) REFERENCES public.iom_schedule_correction(id);


--
-- Name: iom_cyclegram_link iom_cyclegram_link_cyclegram_entry_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_cyclegram_link
    ADD CONSTRAINT iom_cyclegram_link_cyclegram_entry_id_fkey FOREIGN KEY (cyclegram_entry_id) REFERENCES public.service_cyclegram_entry(id);


--
-- Name: iom_cyclegram_link iom_cyclegram_link_synced_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_cyclegram_link
    ADD CONSTRAINT iom_cyclegram_link_synced_by_user_id_fkey FOREIGN KEY (synced_by_user_id) REFERENCES public."user"(id);


--
-- Name: iom_export_log iom_export_log_exported_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_export_log
    ADD CONSTRAINT iom_export_log_exported_by_user_id_fkey FOREIGN KEY (exported_by_user_id) REFERENCES public."user"(id);


--
-- Name: iom_export_log iom_export_log_iom_card_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_export_log
    ADD CONSTRAINT iom_export_log_iom_card_id_fkey FOREIGN KEY (iom_card_id) REFERENCES public.iom_card(id);


--
-- Name: iom_history iom_history_created_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_history
    ADD CONSTRAINT iom_history_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public."user"(id);


--
-- Name: iom_history iom_history_iom_card_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_history
    ADD CONSTRAINT iom_history_iom_card_id_fkey FOREIGN KEY (iom_card_id) REFERENCES public.iom_card(id);


--
-- Name: iom_import_session_schedule iom_import_session_schedule_imported_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_import_session_schedule
    ADD CONSTRAINT iom_import_session_schedule_imported_by_user_id_fkey FOREIGN KEY (imported_by_user_id) REFERENCES public."user"(id);


--
-- Name: iom_import_session_schedule iom_import_session_schedule_iom_card_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_import_session_schedule
    ADD CONSTRAINT iom_import_session_schedule_iom_card_id_fkey FOREIGN KEY (iom_card_id) REFERENCES public.iom_card(id);


--
-- Name: iom_monitoring_entry iom_monitoring_entry_iom_card_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_monitoring_entry
    ADD CONSTRAINT iom_monitoring_entry_iom_card_id_fkey FOREIGN KEY (iom_card_id) REFERENCES public.iom_card(id);


--
-- Name: iom_monitoring_entry iom_monitoring_entry_updated_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_monitoring_entry
    ADD CONSTRAINT iom_monitoring_entry_updated_by_user_id_fkey FOREIGN KEY (updated_by_user_id) REFERENCES public."user"(id);


--
-- Name: iom_schedule_correction iom_schedule_correction_created_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_schedule_correction
    ADD CONSTRAINT iom_schedule_correction_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public."user"(id);


--
-- Name: iom_schedule_correction iom_schedule_correction_iom_card_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_schedule_correction
    ADD CONSTRAINT iom_schedule_correction_iom_card_id_fkey FOREIGN KEY (iom_card_id) REFERENCES public.iom_card(id);


--
-- Name: iom_schedule_correction iom_schedule_correction_specialist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_schedule_correction
    ADD CONSTRAINT iom_schedule_correction_specialist_id_fkey FOREIGN KEY (specialist_id) REFERENCES public.service_specialist(id);


--
-- Name: iom_schedule_correction iom_schedule_correction_updated_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_schedule_correction
    ADD CONSTRAINT iom_schedule_correction_updated_by_user_id_fkey FOREIGN KEY (updated_by_user_id) REFERENCES public."user"(id);


--
-- Name: iom_schedule_lesson iom_schedule_lesson_iom_card_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_schedule_lesson
    ADD CONSTRAINT iom_schedule_lesson_iom_card_id_fkey FOREIGN KEY (iom_card_id) REFERENCES public.iom_card(id);


--
-- Name: iom_section_data iom_section_data_created_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_section_data
    ADD CONSTRAINT iom_section_data_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public."user"(id);


--
-- Name: iom_section_data iom_section_data_iom_card_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_section_data
    ADD CONSTRAINT iom_section_data_iom_card_id_fkey FOREIGN KEY (iom_card_id) REFERENCES public.iom_card(id);


--
-- Name: iom_section_data iom_section_data_updated_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_section_data
    ADD CONSTRAINT iom_section_data_updated_by_user_id_fkey FOREIGN KEY (updated_by_user_id) REFERENCES public."user"(id);


--
-- Name: iom_specialist_plan iom_specialist_plan_assignment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_specialist_plan
    ADD CONSTRAINT iom_specialist_plan_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.service_assignment(id);


--
-- Name: iom_specialist_plan iom_specialist_plan_created_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_specialist_plan
    ADD CONSTRAINT iom_specialist_plan_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public."user"(id);


--
-- Name: iom_specialist_plan iom_specialist_plan_iom_card_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_specialist_plan
    ADD CONSTRAINT iom_specialist_plan_iom_card_id_fkey FOREIGN KEY (iom_card_id) REFERENCES public.iom_card(id);


--
-- Name: iom_specialist_plan iom_specialist_plan_specialist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_specialist_plan
    ADD CONSTRAINT iom_specialist_plan_specialist_id_fkey FOREIGN KEY (specialist_id) REFERENCES public.service_specialist(id);


--
-- Name: iom_specialist_plan iom_specialist_plan_updated_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.iom_specialist_plan
    ADD CONSTRAINT iom_specialist_plan_updated_by_user_id_fkey FOREIGN KEY (updated_by_user_id) REFERENCES public."user"(id);


--
-- Name: mail_settings_log mail_settings_log_created_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mail_settings_log
    ADD CONSTRAINT mail_settings_log_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public."user"(id);


--
-- Name: max_binding max_binding_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.max_binding
    ADD CONSTRAINT max_binding_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: mobile_push_token mobile_push_token_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mobile_push_token
    ADD CONSTRAINT mobile_push_token_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: olympiad_import_session olympiad_import_session_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_import_session
    ADD CONSTRAINT olympiad_import_session_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: olympiad_import_session olympiad_import_session_department_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_import_session
    ADD CONSTRAINT olympiad_import_session_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.department(id);


--
-- Name: olympiad_import_session olympiad_import_session_imported_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_import_session
    ADD CONSTRAINT olympiad_import_session_imported_by_fkey FOREIGN KEY (imported_by) REFERENCES public."user"(id);


--
-- Name: olympiad_import_session olympiad_import_session_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_import_session
    ADD CONSTRAINT olympiad_import_session_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id);


--
-- Name: olympiad_result olympiad_result_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_result
    ADD CONSTRAINT olympiad_result_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: olympiad_result olympiad_result_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_result
    ADD CONSTRAINT olympiad_result_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: olympiad_result olympiad_result_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_result
    ADD CONSTRAINT olympiad_result_created_by_fkey FOREIGN KEY (created_by) REFERENCES public."user"(id);


--
-- Name: olympiad_result olympiad_result_department_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_result
    ADD CONSTRAINT olympiad_result_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.department(id);


--
-- Name: olympiad_result olympiad_result_import_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_result
    ADD CONSTRAINT olympiad_result_import_session_id_fkey FOREIGN KEY (import_session_id) REFERENCES public.olympiad_import_session(id);


--
-- Name: olympiad_result olympiad_result_school_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_result
    ADD CONSTRAINT olympiad_result_school_class_id_fkey FOREIGN KEY (school_class_id) REFERENCES public.school_class(id);


--
-- Name: olympiad_result olympiad_result_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_result
    ADD CONSTRAINT olympiad_result_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id);


--
-- Name: olympiad_result olympiad_result_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_result
    ADD CONSTRAINT olympiad_result_teacher_id_fkey FOREIGN KEY (teacher_id) REFERENCES public."user"(id);


--
-- Name: olympiad_subject_mapping olympiad_subject_mapping_department_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_subject_mapping
    ADD CONSTRAINT olympiad_subject_mapping_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.department(id);


--
-- Name: olympiad_subject_mapping olympiad_subject_mapping_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_subject_mapping
    ADD CONSTRAINT olympiad_subject_mapping_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id);


--
-- Name: olympiad_unmatched_row olympiad_unmatched_row_import_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_unmatched_row
    ADD CONSTRAINT olympiad_unmatched_row_import_session_id_fkey FOREIGN KEY (import_session_id) REFERENCES public.olympiad_import_session(id);


--
-- Name: olympiad_unmatched_row olympiad_unmatched_row_resolved_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_unmatched_row
    ADD CONSTRAINT olympiad_unmatched_row_resolved_child_id_fkey FOREIGN KEY (resolved_child_id) REFERENCES public.child(id);


--
-- Name: olympiad_unmatched_row olympiad_unmatched_row_resolved_department_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_unmatched_row
    ADD CONSTRAINT olympiad_unmatched_row_resolved_department_id_fkey FOREIGN KEY (resolved_department_id) REFERENCES public.department(id);


--
-- Name: olympiad_unmatched_row olympiad_unmatched_row_resolved_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.olympiad_unmatched_row
    ADD CONSTRAINT olympiad_unmatched_row_resolved_teacher_id_fkey FOREIGN KEY (resolved_teacher_id) REFERENCES public."user"(id);


--
-- Name: order_responsible_link order_responsible_link_order_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_responsible_link
    ADD CONSTRAINT order_responsible_link_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.school_order(id);


--
-- Name: order_responsible_link order_responsible_link_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_responsible_link
    ADD CONSTRAINT order_responsible_link_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: order_responsible order_responsible_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.order_responsible
    ADD CONSTRAINT order_responsible_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: page_visit page_visit_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.page_visit
    ADD CONSTRAINT page_visit_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: password_reset_token password_reset_token_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.password_reset_token
    ADD CONSTRAINT password_reset_token_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: preschool_attendance_record preschool_attendance_record_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_attendance_record
    ADD CONSTRAINT preschool_attendance_record_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.preschool_child(id);


--
-- Name: preschool_attendance_record preschool_attendance_record_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_attendance_record
    ADD CONSTRAINT preschool_attendance_record_group_id_fkey FOREIGN KEY (group_id) REFERENCES public.preschool_group(id);


--
-- Name: preschool_attendance_record preschool_attendance_record_upload_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_attendance_record
    ADD CONSTRAINT preschool_attendance_record_upload_id_fkey FOREIGN KEY (upload_id) REFERENCES public.preschool_attendance_upload(id);


--
-- Name: preschool_attendance_upload preschool_attendance_upload_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_attendance_upload
    ADD CONSTRAINT preschool_attendance_upload_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: preschool_child preschool_child_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_child
    ADD CONSTRAINT preschool_child_group_id_fkey FOREIGN KEY (group_id) REFERENCES public.preschool_group(id);


--
-- Name: preschool_child preschool_child_import_batch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_child
    ADD CONSTRAINT preschool_child_import_batch_id_fkey FOREIGN KEY (import_batch_id) REFERENCES public.preschool_children_import(id);


--
-- Name: preschool_child_movement preschool_child_movement_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_child_movement
    ADD CONSTRAINT preschool_child_movement_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.preschool_child(id);


--
-- Name: preschool_child_movement preschool_child_movement_from_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_child_movement
    ADD CONSTRAINT preschool_child_movement_from_academic_year_id_fkey FOREIGN KEY (from_academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: preschool_child_movement preschool_child_movement_from_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_child_movement
    ADD CONSTRAINT preschool_child_movement_from_group_id_fkey FOREIGN KEY (from_group_id) REFERENCES public.preschool_group(id);


--
-- Name: preschool_child_movement preschool_child_movement_to_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_child_movement
    ADD CONSTRAINT preschool_child_movement_to_academic_year_id_fkey FOREIGN KEY (to_academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: preschool_child_movement preschool_child_movement_to_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_child_movement
    ADD CONSTRAINT preschool_child_movement_to_group_id_fkey FOREIGN KEY (to_group_id) REFERENCES public.preschool_group(id);


--
-- Name: preschool_children_import preschool_children_import_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_children_import
    ADD CONSTRAINT preschool_children_import_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: preschool_group preschool_group_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_group
    ADD CONSTRAINT preschool_group_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: preschool_group preschool_group_building_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_group
    ADD CONSTRAINT preschool_group_building_id_fkey FOREIGN KEY (building_id) REFERENCES public.buildings(id);


--
-- Name: preschool_group preschool_group_teacher_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_group
    ADD CONSTRAINT preschool_group_teacher_user_id_fkey FOREIGN KEY (teacher_user_id) REFERENCES public."user"(id);


--
-- Name: preschool_representative preschool_representative_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.preschool_representative
    ADD CONSTRAINT preschool_representative_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.preschool_child(id);


--
-- Name: saved_view saved_view_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.saved_view
    ADD CONSTRAINT saved_view_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: school_class school_class_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_class
    ADD CONSTRAINT school_class_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: school_class school_class_building_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_class
    ADD CONSTRAINT school_class_building_id_fkey FOREIGN KEY (building_id) REFERENCES public.buildings(id);


--
-- Name: school_class school_class_teacher_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_class
    ADD CONSTRAINT school_class_teacher_user_id_fkey FOREIGN KEY (teacher_user_id) REFERENCES public."user"(id);


--
-- Name: school_order school_order_created_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_order
    ADD CONSTRAINT school_order_created_by_id_fkey FOREIGN KEY (created_by_id) REFERENCES public."user"(id);


--
-- Name: school_order school_order_responsible_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_order
    ADD CONSTRAINT school_order_responsible_user_id_fkey FOREIGN KEY (responsible_user_id) REFERENCES public."user"(id);


--
-- Name: school_plan_event school_plan_event_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_plan_event
    ADD CONSTRAINT school_plan_event_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: school_plan_event school_plan_event_building_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_plan_event
    ADD CONSTRAINT school_plan_event_building_id_fkey FOREIGN KEY (building_id) REFERENCES public.buildings(id);


--
-- Name: school_plan_event school_plan_event_category_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_plan_event
    ADD CONSTRAINT school_plan_event_category_id_fkey FOREIGN KEY (category_id) REFERENCES public.school_plan_category(id);


--
-- Name: school_plan_event school_plan_event_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_plan_event
    ADD CONSTRAINT school_plan_event_class_id_fkey FOREIGN KEY (class_id) REFERENCES public.school_class(id);


--
-- Name: school_plan_event school_plan_event_created_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_plan_event
    ADD CONSTRAINT school_plan_event_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public."user"(id);


--
-- Name: school_plan_event school_plan_event_direction_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_plan_event
    ADD CONSTRAINT school_plan_event_direction_id_fkey FOREIGN KEY (direction_id) REFERENCES public.school_plan_direction(id);


--
-- Name: school_plan_event school_plan_event_responsible_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_plan_event
    ADD CONSTRAINT school_plan_event_responsible_user_id_fkey FOREIGN KEY (responsible_user_id) REFERENCES public."user"(id);


--
-- Name: school_plan_event school_plan_event_updated_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.school_plan_event
    ADD CONSTRAINT school_plan_event_updated_by_user_id_fkey FOREIGN KEY (updated_by_user_id) REFERENCES public."user"(id);


--
-- Name: service_assignment service_assignment_building_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_assignment
    ADD CONSTRAINT service_assignment_building_id_fkey FOREIGN KEY (building_id) REFERENCES public.buildings(id);


--
-- Name: service_assignment service_assignment_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_assignment
    ADD CONSTRAINT service_assignment_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: service_assignment service_assignment_created_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_assignment
    ADD CONSTRAINT service_assignment_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public."user"(id);


--
-- Name: service_assignment_history service_assignment_history_assignment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_assignment_history
    ADD CONSTRAINT service_assignment_history_assignment_id_fkey FOREIGN KEY (assignment_id) REFERENCES public.service_assignment(id);


--
-- Name: service_assignment_history service_assignment_history_changed_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_assignment_history
    ADD CONSTRAINT service_assignment_history_changed_by_user_id_fkey FOREIGN KEY (changed_by_user_id) REFERENCES public."user"(id);


--
-- Name: service_assignment service_assignment_incident_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_assignment
    ADD CONSTRAINT service_assignment_incident_id_fkey FOREIGN KEY (incident_id) REFERENCES public.incident(id);


--
-- Name: service_assignment service_assignment_specialist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_assignment
    ADD CONSTRAINT service_assignment_specialist_id_fkey FOREIGN KEY (specialist_id) REFERENCES public.service_specialist(id);


--
-- Name: service_cyclegram service_cyclegram_copied_from_cyclegram_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_cyclegram
    ADD CONSTRAINT service_cyclegram_copied_from_cyclegram_id_fkey FOREIGN KEY (copied_from_cyclegram_id) REFERENCES public.service_cyclegram(id);


--
-- Name: service_cyclegram service_cyclegram_created_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_cyclegram
    ADD CONSTRAINT service_cyclegram_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public."user"(id);


--
-- Name: service_cyclegram_entry service_cyclegram_entry_activity_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_cyclegram_entry
    ADD CONSTRAINT service_cyclegram_entry_activity_type_id_fkey FOREIGN KEY (activity_type_id) REFERENCES public.service_activity_type(id);


--
-- Name: service_cyclegram_entry service_cyclegram_entry_building_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_cyclegram_entry
    ADD CONSTRAINT service_cyclegram_entry_building_id_fkey FOREIGN KEY (building_id) REFERENCES public.buildings(id);


--
-- Name: service_cyclegram_entry service_cyclegram_entry_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_cyclegram_entry
    ADD CONSTRAINT service_cyclegram_entry_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: service_cyclegram_entry service_cyclegram_entry_cyclegram_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_cyclegram_entry
    ADD CONSTRAINT service_cyclegram_entry_cyclegram_id_fkey FOREIGN KEY (cyclegram_id) REFERENCES public.service_cyclegram(id);


--
-- Name: service_cyclegram_history service_cyclegram_history_changed_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_cyclegram_history
    ADD CONSTRAINT service_cyclegram_history_changed_by_user_id_fkey FOREIGN KEY (changed_by_user_id) REFERENCES public."user"(id);


--
-- Name: service_cyclegram_history service_cyclegram_history_cyclegram_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_cyclegram_history
    ADD CONSTRAINT service_cyclegram_history_cyclegram_id_fkey FOREIGN KEY (cyclegram_id) REFERENCES public.service_cyclegram(id);


--
-- Name: service_cyclegram service_cyclegram_specialist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_cyclegram
    ADD CONSTRAINT service_cyclegram_specialist_id_fkey FOREIGN KEY (specialist_id) REFERENCES public.service_specialist(id);


--
-- Name: service_cyclegram service_cyclegram_updated_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_cyclegram
    ADD CONSTRAINT service_cyclegram_updated_by_user_id_fkey FOREIGN KEY (updated_by_user_id) REFERENCES public."user"(id);


--
-- Name: service_import_unmatched_staff service_import_unmatched_staff_matched_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_import_unmatched_staff
    ADD CONSTRAINT service_import_unmatched_staff_matched_by_user_id_fkey FOREIGN KEY (matched_by_user_id) REFERENCES public."user"(id);


--
-- Name: service_import_unmatched_staff service_import_unmatched_staff_matched_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_import_unmatched_staff
    ADD CONSTRAINT service_import_unmatched_staff_matched_user_id_fkey FOREIGN KEY (matched_user_id) REFERENCES public."user"(id);


--
-- Name: service_presentation_block service_presentation_block_executor_specialist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation_block
    ADD CONSTRAINT service_presentation_block_executor_specialist_id_fkey FOREIGN KEY (executor_specialist_id) REFERENCES public.service_specialist(id);


--
-- Name: service_presentation_block service_presentation_block_executor_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation_block
    ADD CONSTRAINT service_presentation_block_executor_user_id_fkey FOREIGN KEY (executor_user_id) REFERENCES public."user"(id);


--
-- Name: service_presentation_block service_presentation_block_presentation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation_block
    ADD CONSTRAINT service_presentation_block_presentation_id_fkey FOREIGN KEY (presentation_id) REFERENCES public.service_presentation(id);


--
-- Name: service_presentation_block service_presentation_block_updated_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation_block
    ADD CONSTRAINT service_presentation_block_updated_by_user_id_fkey FOREIGN KEY (updated_by_user_id) REFERENCES public."user"(id);


--
-- Name: service_presentation service_presentation_building_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation
    ADD CONSTRAINT service_presentation_building_id_fkey FOREIGN KEY (building_id) REFERENCES public.buildings(id);


--
-- Name: service_presentation service_presentation_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation
    ADD CONSTRAINT service_presentation_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: service_presentation_history service_presentation_history_block_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation_history
    ADD CONSTRAINT service_presentation_history_block_id_fkey FOREIGN KEY (block_id) REFERENCES public.service_presentation_block(id);


--
-- Name: service_presentation_history service_presentation_history_presentation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation_history
    ADD CONSTRAINT service_presentation_history_presentation_id_fkey FOREIGN KEY (presentation_id) REFERENCES public.service_presentation(id);


--
-- Name: service_presentation_history service_presentation_history_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation_history
    ADD CONSTRAINT service_presentation_history_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: service_presentation service_presentation_initiator_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation
    ADD CONSTRAINT service_presentation_initiator_user_id_fkey FOREIGN KEY (initiator_user_id) REFERENCES public."user"(id);


--
-- Name: service_presentation service_presentation_last_changed_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation
    ADD CONSTRAINT service_presentation_last_changed_by_user_id_fkey FOREIGN KEY (last_changed_by_user_id) REFERENCES public."user"(id);


--
-- Name: service_presentation service_presentation_methodist_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation
    ADD CONSTRAINT service_presentation_methodist_user_id_fkey FOREIGN KEY (methodist_user_id) REFERENCES public."user"(id);


--
-- Name: service_presentation service_presentation_school_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_presentation
    ADD CONSTRAINT service_presentation_school_class_id_fkey FOREIGN KEY (school_class_id) REFERENCES public.school_class(id);


--
-- Name: service_rate_norm service_rate_norm_building_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_rate_norm
    ADD CONSTRAINT service_rate_norm_building_id_fkey FOREIGN KEY (building_id) REFERENCES public.buildings(id);


--
-- Name: service_rate_norm service_rate_norm_specialization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_rate_norm
    ADD CONSTRAINT service_rate_norm_specialization_id_fkey FOREIGN KEY (specialization_id) REFERENCES public.service_specialization(id);


--
-- Name: service_responsible service_responsible_assigned_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_responsible
    ADD CONSTRAINT service_responsible_assigned_by_user_id_fkey FOREIGN KEY (assigned_by_user_id) REFERENCES public."user"(id);


--
-- Name: service_responsible service_responsible_specialist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_responsible
    ADD CONSTRAINT service_responsible_specialist_id_fkey FOREIGN KEY (specialist_id) REFERENCES public.service_specialist(id);


--
-- Name: service_specialist_building service_specialist_building_building_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_specialist_building
    ADD CONSTRAINT service_specialist_building_building_id_fkey FOREIGN KEY (building_id) REFERENCES public.buildings(id);


--
-- Name: service_specialist_building service_specialist_building_specialist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_specialist_building
    ADD CONSTRAINT service_specialist_building_specialist_id_fkey FOREIGN KEY (specialist_id) REFERENCES public.service_specialist(id);


--
-- Name: service_specialist service_specialist_main_building_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_specialist
    ADD CONSTRAINT service_specialist_main_building_id_fkey FOREIGN KEY (main_building_id) REFERENCES public.buildings(id);


--
-- Name: service_specialist_specialization service_specialist_specialization_specialist_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_specialist_specialization
    ADD CONSTRAINT service_specialist_specialization_specialist_id_fkey FOREIGN KEY (specialist_id) REFERENCES public.service_specialist(id);


--
-- Name: service_specialist_specialization service_specialist_specialization_specialization_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_specialist_specialization
    ADD CONSTRAINT service_specialist_specialization_specialization_id_fkey FOREIGN KEY (specialization_id) REFERENCES public.service_specialization(id);


--
-- Name: service_specialist service_specialist_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_specialist
    ADD CONSTRAINT service_specialist_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: support_case support_case_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_case
    ADD CONSTRAINT support_case_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: support_case support_case_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_case
    ADD CONSTRAINT support_case_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: support_case support_case_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.support_case
    ADD CONSTRAINT support_case_created_by_fkey FOREIGN KEY (created_by) REFERENCES public."user"(id);


--
-- Name: system_log system_log_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_log
    ADD CONSTRAINT system_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: system_mail_settings system_mail_settings_updated_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_mail_settings
    ADD CONSTRAINT system_mail_settings_updated_by_user_id_fkey FOREIGN KEY (updated_by_user_id) REFERENCES public."user"(id);


--
-- Name: task task_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task
    ADD CONSTRAINT task_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: task_attachment task_attachment_deleted_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_attachment
    ADD CONSTRAINT task_attachment_deleted_by_user_id_fkey FOREIGN KEY (deleted_by_user_id) REFERENCES public."user"(id);


--
-- Name: task_attachment task_attachment_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_attachment
    ADD CONSTRAINT task_attachment_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.task(id);


--
-- Name: task_attachment task_attachment_uploaded_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_attachment
    ADD CONSTRAINT task_attachment_uploaded_by_user_id_fkey FOREIGN KEY (uploaded_by_user_id) REFERENCES public."user"(id);


--
-- Name: task_checklist_item task_checklist_item_completed_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_checklist_item
    ADD CONSTRAINT task_checklist_item_completed_by_user_id_fkey FOREIGN KEY (completed_by_user_id) REFERENCES public."user"(id);


--
-- Name: task_checklist_item task_checklist_item_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_checklist_item
    ADD CONSTRAINT task_checklist_item_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.task(id);


--
-- Name: task task_child_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task
    ADD CONSTRAINT task_child_id_fkey FOREIGN KEY (child_id) REFERENCES public.child(id);


--
-- Name: task task_class_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task
    ADD CONSTRAINT task_class_id_fkey FOREIGN KEY (class_id) REFERENCES public.school_class(id);


--
-- Name: task_comment task_comment_author_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_comment
    ADD CONSTRAINT task_comment_author_user_id_fkey FOREIGN KEY (author_user_id) REFERENCES public."user"(id);


--
-- Name: task_comment task_comment_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_comment
    ADD CONSTRAINT task_comment_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.task(id);


--
-- Name: task task_controller_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task
    ADD CONSTRAINT task_controller_user_id_fkey FOREIGN KEY (controller_user_id) REFERENCES public."user"(id);


--
-- Name: task task_creator_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task
    ADD CONSTRAINT task_creator_user_id_fkey FOREIGN KEY (creator_user_id) REFERENCES public."user"(id);


--
-- Name: task_email_log task_email_log_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_email_log
    ADD CONSTRAINT task_email_log_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.task(id);


--
-- Name: task_email_log task_email_log_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_email_log
    ADD CONSTRAINT task_email_log_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: task_history task_history_actor_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_history
    ADD CONSTRAINT task_history_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public."user"(id);


--
-- Name: task_history task_history_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_history
    ADD CONSTRAINT task_history_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.task(id);


--
-- Name: task task_incident_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task
    ADD CONSTRAINT task_incident_id_fkey FOREIGN KEY (incident_id) REFERENCES public.incident(id);


--
-- Name: task_notification task_notification_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_notification
    ADD CONSTRAINT task_notification_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.task(id);


--
-- Name: task_notification task_notification_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_notification
    ADD CONSTRAINT task_notification_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: task task_parent_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task
    ADD CONSTRAINT task_parent_task_id_fkey FOREIGN KEY (parent_task_id) REFERENCES public.task(id);


--
-- Name: task_participant task_participant_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_participant
    ADD CONSTRAINT task_participant_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.task(id);


--
-- Name: task_participant task_participant_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_participant
    ADD CONSTRAINT task_participant_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: task task_responsible_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task
    ADD CONSTRAINT task_responsible_user_id_fkey FOREIGN KEY (responsible_user_id) REFERENCES public."user"(id);


--
-- Name: task task_task_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task
    ADD CONSTRAINT task_task_type_id_fkey FOREIGN KEY (task_type_id) REFERENCES public.task_type(id);


--
-- Name: task_template_checklist_item task_template_checklist_item_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_template_checklist_item
    ADD CONSTRAINT task_template_checklist_item_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.task_template(id);


--
-- Name: task_template task_template_created_by_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_template
    ADD CONSTRAINT task_template_created_by_user_id_fkey FOREIGN KEY (created_by_user_id) REFERENCES public."user"(id);


--
-- Name: task_template task_template_task_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_template
    ADD CONSTRAINT task_template_task_type_id_fkey FOREIGN KEY (task_type_id) REFERENCES public.task_type(id);


--
-- Name: teacher_course teacher_course_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teacher_course
    ADD CONSTRAINT teacher_course_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: teacher_course teacher_course_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teacher_course
    ADD CONSTRAINT teacher_course_teacher_id_fkey FOREIGN KEY (teacher_id) REFERENCES public."user"(id);


--
-- Name: teacher_load teacher_load_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teacher_load
    ADD CONSTRAINT teacher_load_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: teacher_load teacher_load_building_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teacher_load
    ADD CONSTRAINT teacher_load_building_id_fkey FOREIGN KEY (building_id) REFERENCES public.buildings(id);


--
-- Name: teacher_load teacher_load_department_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teacher_load
    ADD CONSTRAINT teacher_load_department_id_fkey FOREIGN KEY (department_id) REFERENCES public.department(id);


--
-- Name: teacher_load teacher_load_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teacher_load
    ADD CONSTRAINT teacher_load_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id);


--
-- Name: teacher_load teacher_load_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teacher_load
    ADD CONSTRAINT teacher_load_teacher_id_fkey FOREIGN KEY (teacher_id) REFERENCES public."user"(id);


--
-- Name: teacher_mcko_result teacher_mcko_result_academic_year_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teacher_mcko_result
    ADD CONSTRAINT teacher_mcko_result_academic_year_id_fkey FOREIGN KEY (academic_year_id) REFERENCES public.academic_year(id);


--
-- Name: teacher_mcko_result teacher_mcko_result_subject_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teacher_mcko_result
    ADD CONSTRAINT teacher_mcko_result_subject_id_fkey FOREIGN KEY (subject_id) REFERENCES public.subject(id);


--
-- Name: teacher_mcko_result teacher_mcko_result_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teacher_mcko_result
    ADD CONSTRAINT teacher_mcko_result_teacher_id_fkey FOREIGN KEY (teacher_id) REFERENCES public."user"(id);


--
-- Name: user_building user_building_building_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_building
    ADD CONSTRAINT user_building_building_id_fkey FOREIGN KEY (building_id) REFERENCES public.buildings(id);


--
-- Name: user_building user_building_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_building
    ADD CONSTRAINT user_building_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: user_import_row user_import_row_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_import_row
    ADD CONSTRAINT user_import_row_session_id_fkey FOREIGN KEY (session_id) REFERENCES public.user_import_session(id);


--
-- Name: user_import_row user_import_row_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_import_row
    ADD CONSTRAINT user_import_row_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: user_import_session user_import_session_imported_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_import_session
    ADD CONSTRAINT user_import_session_imported_by_fkey FOREIGN KEY (imported_by) REFERENCES public."user"(id);


--
-- Name: user_import_session user_import_session_reverted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_import_session
    ADD CONSTRAINT user_import_session_reverted_by_fkey FOREIGN KEY (reverted_by) REFERENCES public."user"(id);


--
-- Name: user_role user_role_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_role
    ADD CONSTRAINT user_role_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.role(id);


--
-- Name: user_role user_role_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_role
    ADD CONSTRAINT user_role_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- PostgreSQL database dump complete
--
