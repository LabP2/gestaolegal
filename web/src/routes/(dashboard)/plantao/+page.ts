import { redirect } from '@sveltejs/kit';

/** O item "Plantão" do menu só agrupa subrotas; a URL digitada cai nas escalas. */
export const load = () => {
	redirect(307, '/plantao/escalas');
};
