export const base_url: string = process.env.BASE_URL ?? " ";
export const validEmail: string = process.env.EMAIL ?? " ";
export const validPassword: string = process.env.PASSWORD
  ? process.env.PASSWORD
  : " ";
export const invalidEmail: string = process.env.INVALID_EMAIL
  ? process.env.INVALID_EMAIL
  : " ";
export const loginUrl: string = process.env.LOGIN_URL
  ? process.env.LOGIN_URL
  : " ";
