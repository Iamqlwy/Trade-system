export interface Feedback {
  id: number
  type: 'bug' | 'feature' | 'question' | 'other'
  title: string
  status: 'pending' | 'in_progress' | 'resolved' | 'closed'
  created_at: string
}

export interface FeedbackDetail extends Feedback {
  content: string
  admin_reply: string | null
  replied_at: string | null
}

export interface FeedbackSubmit {
  type: string
  title: string
  content: string
}

export interface AdminFeedbackItem extends FeedbackDetail {
  user_id: number
  username: string
  replied_by: number | null
  replied_by_name: string | null
}

export interface FeedbackCounts {
  total: number
  pending: number
  in_progress: number
  resolved: number
  closed: number
}
