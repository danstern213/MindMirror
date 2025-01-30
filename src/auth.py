import streamlit as st
from supabase import create_client

class Auth:
    def __init__(self):
        self.supabase = create_client(
            st.secrets["SUPABASE_URL"],
            st.secrets["SUPABASE_KEY"]
        )

    def render_auth(self):
        """Render the authentication UI."""
        if 'user' not in st.session_state:
            st.session_state.user = None

        else st.session_state.user is None:
            tab1, tab2 = st.tabs(["Login", "Sign Up"])
            
            with tab1:
                with st.form("login_form"):
                    email = st.text_input("Email")
                    password = st.text_input("Password", type="password")
                    if st.form_submit_button("Login"):
                        try:
                            response = self.supabase.auth.sign_in_with_password({
                                "email": email,
                                "password": password
                            })
                            st.session_state.user = response.user
                            st.success("Logged in successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Login failed: {str(e)}")

            with tab2:
                with st.form("signup_form"):
                    email = st.text_input("Email")
                    password = st.text_input("Password", type="password")
                    password_confirm = st.text_input("Confirm Password", type="password")
                    if st.form_submit_button("Sign Up"):
                        if password != password_confirm:
                            st.error("Passwords do not match")
                        else:
                            try:
                                response = self.supabase.auth.sign_up({
                                    "email": email,
                                    "password": password
                                })
                                st.success("Signed up successfully! Please check your email to verify your account.")
                            except Exception as e:
                                st.error(f"Signup failed: {str(e)}")

        # else:
        #     st.write(f"Logged in as: {st.session_state.user.email}")
        #     if st.button("Logout"):
        #         self.supabase.auth.sign_out()
        #         st.session_state.user = None
        #         st.rerun()

    def get_user_id(self) -> str:
        """Get the current user's ID."""
        return st.session_state.user.id if st.session_state.user else None 