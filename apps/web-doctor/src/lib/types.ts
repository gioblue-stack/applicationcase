// Типы ответов API — из OpenAPI бэкенда (npm run api:types).
import type { components } from "./api-schema";

type S = components["schemas"];

export type QueueItem = S["QueueItem"];
export type OpenFlag = S["OpenFlag"];
export type PatientCard = S["PatientCardSummary"];
export type DiaryChart = S["DiaryChart"];
export type DiarySeries = S["DiarySeries"];
export type TreatmentMarker = S["TreatmentMarker"];
export type InstrumentHistory = S["InstrumentHistory"];
export type QuestionnairePoint = S["QuestionnairePoint"];
export type PrescriptionAdherence = S["PrescriptionAdherence"];
export type AdherenceSummary = S["AdherenceSummary"];
export type SideEffectEntry = S["SideEffectEntry"];
export type RiskAssessmentView = S["RiskAssessmentView"];
export type SafetyPlanView = S["SafetyPlanView"];
export type FlagOut = S["FlagOut"];
export type Period = "week" | "month" | "all";
