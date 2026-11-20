import z from 'zod/v4';

export const loginSchema = z.object({
	email: z
		.string()
		.trim()
		.pipe(z.email({ message: 'Email inválido' })),
	password: z.string({ message: 'Senha inválida' })
});

export type LoginSchema = typeof loginSchema;
export type LoginData = z.infer<typeof loginSchema>;
